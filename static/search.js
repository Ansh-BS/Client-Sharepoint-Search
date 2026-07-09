let fuse = null;
let clients = [];
let results = [];
let selectedIndex = -1;
let queryLower = "";
let lastQuery = "";

const MAX_RESULTS = 8;
const FUZZY_MIN_QUERY = 2;
const LEV_MIN_QUERY = 3;
const LEV_MAX_DISTANCE_CAP = 3;
const RECENT_KEY = "sp-search:recent";
const RECENT_MAX = 3;

function isValidLink(link) {
  return link && /^https?:\/\//i.test(link);
}

function openResult(item) {
  if (item && isValidLink(item.link)) {
    recordRecent(lastQuery);
    window.open(item.link, "_blank", "noopener");
  }
}

async function init() {
  try {
    const res = await fetch("/api/clients");
    if (res.status === 401) { window.location = "/login"; return; }
    const raw = await res.json();
    clients = raw.map((c) => {
      const nameStr = c.name == null ? "" : String(c.name);
      const idStr = c.id == null ? "" : String(c.id);
      const nameTokens = [];
      for (const match of nameStr.matchAll(/\S+/g)) {
        const start = match.index;
        nameTokens.push({
          tokenLower: match[0].toLowerCase(),
          start,
          end: start + match[0].length,
        });
      }
      return Object.assign({}, c, {
        nameStr,
        idStr,
        nameLower: nameStr.toLowerCase(),
        idLower: idStr.toLowerCase(),
        nameTokens,
      });
    });
    fuse = new Fuse(clients, {
      keys: [{ name: "name", weight: 0.7 }, { name: "id", weight: 0.3 }],
      threshold: 0.25,
      ignoreLocation: true,
      includeScore: true,
      includeMatches: true,
    });
    const box = document.getElementById("search");
    box.disabled = false;
    box.focus();
  } catch (err) {
    const list = document.getElementById("results");
    const li = document.createElement("li");
    li.className = "error";
    li.textContent = "Could not load client list. Check your connection and reload the page.";
    list.appendChild(li);
  }
}

function clearResults() {
  results = [];
  selectedIndex = -1;
  document.getElementById("results").innerHTML = "";
}

function showRecent() {
  const recent = loadRecent();
  results = recent.map((q) => ({ kind: "recent", query: q }));
  selectedIndex = -1;
  if (results.length === 0) {
    // no recents: clear directly, do NOT fall through to render()'s
    // "No client found" empty-state (that's for a non-empty query with 0 hits)
    document.getElementById("results").innerHTML = "";
    return;
  }
  render();
}

function applyRecent(query) {
  const box = document.getElementById("search");
  box.value = query;
  box.focus();
  search(query);
}

// Greedy leftmost two-pointer scan: takes the earliest field position for each
// query char. Not guaranteed to minimize total gap, but cheap and stable, and
// fieldScore below ranks on the positions this returns.
function subsequencePositions(qLower, fieldLower) {
  if (qLower.length === 0 || qLower.length > fieldLower.length) return null;
  const positions = [];
  let qi = 0;
  for (let fi = 0; fi < fieldLower.length; fi++) {
    if (fieldLower[fi] === qLower[qi]) {
      positions.push(fi);
      qi++;
      if (qi === qLower.length) return positions;
    }
  }
  return null;
}

function fieldScore(positions) {
  const last = positions.length - 1;
  return positions[0] + (positions[last] - positions[0]) - (positions.length - 1);
}

// Space-optimized Levenshtein: two rolling 1-D rows instead of a full matrix.
function levenshtein(a, b) {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  let prev = new Array(b.length + 1);
  let curr = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) prev[j] = j;
  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    const tmp = prev;
    prev = curr;
    curr = tmp;
  }
  return prev[b.length];
}

function maxAllowedDistance(qLen) {
  return Math.min(LEV_MAX_DISTANCE_CAP, Math.ceil(qLen / 4));
}

// Recent searches live in localStorage: this app shares one staff login, so
// there's no per-user server history to key off. Every access is wrapped in
// try/catch because storage can be disabled/unavailable and must never throw.
function loadRecent() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const clean = parsed.filter((q) => typeof q === "string" && q.trim() !== "");
    return clean.slice(0, RECENT_MAX);
  } catch (err) {
    return [];
  }
}

function saveRecent(list) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)));
  } catch (err) {
    // storage disabled/full — silently drop, recents are non-essential
  }
}

function recordRecent(query) {
  const trimmed = query.trim();
  if (!trimmed) return;
  const lowered = trimmed.toLowerCase();
  const existing = loadRecent().filter((q) => q.toLowerCase() !== lowered);
  existing.unshift(trimmed);
  saveRecent(existing);
}

function search(rawQuery) {
  const query = rawQuery.trim();
  lastQuery = query;
  queryLower = query.toLowerCase();
  if (!queryLower) {
    clearResults();
    showRecent();
    return;
  }

  const tier1 = [];
  const tier2 = [];
  // dedup by object identity: robust against missing/duplicate ids, and Fuse
  // returns the same client references so tier-3 fill can skip earlier tiers.
  const seen = new Set();

  for (const c of clients) {
    const prefix = c.nameLower.startsWith(queryLower) || c.idLower.startsWith(queryLower);
    if (prefix) {
      tier1.push({ item: c, tier: 1 });
      seen.add(c);
      continue;
    }
    // plain indexOf, never a regex, so query chars like ( . + are inert
    const substring = c.nameLower.indexOf(queryLower) >= 0 || c.idLower.indexOf(queryLower) >= 0;
    if (substring) {
      tier2.push({ item: c, tier: 2 });
      seen.add(c);
    }
  }

  tier1.sort((a, b) => a.item.nameLower.localeCompare(b.item.nameLower));
  tier2.sort((a, b) => a.item.nameLower.localeCompare(b.item.nameLower));
  results = tier1.concat(tier2).slice(0, MAX_RESULTS);

  if (results.length < MAX_RESULTS) {
    const tier3 = [];
    for (const c of clients) {
      if (seen.has(c)) continue;
      const namePos = subsequencePositions(queryLower, c.nameLower);
      const idPos = subsequencePositions(queryLower, c.idLower);
      if (!namePos && !idPos) continue;
      let score = Infinity;
      if (namePos) score = Math.min(score, fieldScore(namePos));
      if (idPos) score = Math.min(score, fieldScore(idPos));
      tier3.push({ item: c, tier: 3, namePos, idPos, score });
    }
    tier3.sort((a, b) =>
      a.score - b.score || a.item.nameLower.localeCompare(b.item.nameLower));
    for (const entry of tier3) {
      if (results.length >= MAX_RESULTS) break;
      seen.add(entry.item);
      results.push(entry);
    }
  }

  if (results.length < MAX_RESULTS && queryLower.length >= LEV_MIN_QUERY) {
    const maxDist = maxAllowedDistance(queryLower.length);
    const tier4 = [];
    for (const c of clients) {
      if (seen.has(c)) continue;

      // Name side: score each token first, then the whole field. Strictly-less-than
      // comparison throughout means an earlier (token) win at a given distance is
      // never overwritten by a later candidate at the same distance — so a matched
      // token span is preferred over the equal-distance whole-field span.
      let nameBest = Infinity;
      let nameSpan = null;
      for (const tok of c.nameTokens) {
        // |len(a) - len(b)| is a lower bound on edit distance, so skip the call
        // when that bound alone already exceeds maxDist.
        if (Math.abs(tok.tokenLower.length - queryLower.length) > maxDist) continue;
        const d = levenshtein(queryLower, tok.tokenLower);
        if (d < nameBest) {
          nameBest = d;
          nameSpan = [tok.start, tok.end];
        }
      }
      if (Math.abs(c.nameLower.length - queryLower.length) <= maxDist) {
        const d = levenshtein(queryLower, c.nameLower);
        if (d < nameBest) {
          nameBest = d;
          nameSpan = [0, c.nameStr.length];
        }
      }

      let idBest = Infinity;
      if (Math.abs(c.idLower.length - queryLower.length) <= maxDist) {
        idBest = levenshtein(queryLower, c.idLower);
      }

      const score = Math.min(nameBest, idBest);
      if (score > maxDist) continue;

      tier4.push({
        item: c,
        tier: 4,
        score,
        nameSpan: nameBest <= maxDist ? nameSpan : null,
        idSpan: idBest <= maxDist ? [0, c.idStr.length] : null,
      });
    }
    tier4.sort((a, b) =>
      a.score - b.score || a.item.nameLower.localeCompare(b.item.nameLower));
    for (const entry of tier4) {
      if (results.length >= MAX_RESULTS) break;
      seen.add(entry.item);
      results.push(entry);
    }
  }

  if (results.length < MAX_RESULTS && query.length >= FUZZY_MIN_QUERY && fuse) {
    for (const r of fuse.search(query)) {
      if (results.length >= MAX_RESULTS) break;
      if (seen.has(r.item)) continue;
      seen.add(r.item);
      results.push({ item: r.item, tier: 5, matches: r.matches });
    }
  }

  selectedIndex = -1;
  render();
}

function spanForPlain(fieldLower) {
  if (!queryLower) return null;
  const start = fieldLower.indexOf(queryLower);
  if (start < 0) return null;
  return [start, start + queryLower.length];
}

function spanForFuzzy(matches, key) {
  if (!matches) return null;
  const match = matches.find((m) => m.key === key);
  if (!match || !match.indices || !match.indices.length) return null;
  let best = null;
  for (const pair of match.indices) {
    if (!best || (pair[1] - pair[0]) > (best[1] - best[0])) best = pair;
  }
  if (!best) return null;
  // Fuse's end index is inclusive, so the slice end is best[1] + 1
  const span = [best[0], best[1] + 1];
  if (span[1] - span[0] < 2) return null;
  return span;
}

function fillField(el, text, span) {
  el.textContent = "";
  if (!span) {
    el.textContent = text;
    return;
  }
  const before = text.slice(0, span[0]);
  const matchText = text.slice(span[0], span[1]);
  const after = text.slice(span[1]);
  if (before) el.appendChild(document.createTextNode(before));
  const mark = document.createElement("mark");
  mark.className = "match";
  mark.textContent = matchText;
  el.appendChild(mark);
  if (after) el.appendChild(document.createTextNode(after));
}

function fillFieldPositions(el, text, positions) {
  el.textContent = "";
  if (!positions || !positions.length) {
    el.textContent = text;
    return;
  }
  // positions is ascending; coalesce consecutive matched indices into one <mark>
  const matched = new Set(positions);
  let buffer = "";
  let markText = "";
  for (let i = 0; i < text.length; i++) {
    if (matched.has(i)) {
      if (buffer) {
        el.appendChild(document.createTextNode(buffer));
        buffer = "";
      }
      markText += text[i];
    } else {
      if (markText) {
        const mark = document.createElement("mark");
        mark.className = "match";
        mark.textContent = markText;
        el.appendChild(mark);
        markText = "";
      }
      buffer += text[i];
    }
  }
  if (markText) {
    const mark = document.createElement("mark");
    mark.className = "match";
    mark.textContent = markText;
    el.appendChild(mark);
  }
  if (buffer) el.appendChild(document.createTextNode(buffer));
}

function render() {
  const list = document.getElementById("results");
  list.innerHTML = "";
  if (!results.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No client found";
    list.appendChild(li);
    return;
  }

  results.forEach((entry, index) => {
    if (entry.kind === "recent") {
      const li = document.createElement("li");
      li.className = "recent";
      const label = document.createElement("span");
      label.className = "recent-label";
      label.textContent = "Recent";
      const q = document.createElement("span");
      q.className = "recent-query";
      q.textContent = entry.query;
      li.append(label, q);
      li.addEventListener("click", () => applyRecent(entry.query));
      li.addEventListener("mouseenter", () => setSelected(index));
      list.appendChild(li);
      return;
    }

    const item = entry.item;
    const li = document.createElement("li");

    const info = document.createElement("div");
    info.className = "info";

    const name = document.createElement("span");
    name.className = "name";
    const id = document.createElement("span");
    id.className = "cid";

    if (entry.tier === 3) {
      fillFieldPositions(name, item.nameStr, entry.namePos);
      fillFieldPositions(id, item.idStr, entry.idPos);
    } else if (entry.tier === 4) {
      fillField(name, item.nameStr, entry.nameSpan);
      fillField(id, item.idStr, entry.idSpan);
    } else if (entry.tier === 5) {
      fillField(name, item.nameStr, spanForFuzzy(entry.matches, "name"));
      fillField(id, item.idStr, spanForFuzzy(entry.matches, "id"));
    } else {
      fillField(name, item.nameStr, spanForPlain(item.nameLower));
      fillField(id, item.idStr, spanForPlain(item.idLower));
    }

    info.append(name, id);
    li.appendChild(info);

    if (isValidLink(item.link)) {
      const a = document.createElement("a");
      a.href = item.link;
      a.target = "_blank";
      a.rel = "noopener";
      a.className = "open";
      a.textContent = "Open folder";
      a.addEventListener("click", (e) => { e.preventDefault(); openResult(item); });
      li.appendChild(a);
    } else {
      const badge = document.createElement("span");
      badge.className = "nolink";
      badge.textContent = "No link on file";
      li.appendChild(badge);
    }

    li.addEventListener("mouseenter", () => setSelected(index));
    list.appendChild(li);
  });
}

function setSelected(i) {
  const lis = document.getElementById("results").querySelectorAll("li");
  if (selectedIndex >= 0 && lis[selectedIndex]) {
    lis[selectedIndex].classList.remove("selected");
    lis[selectedIndex].removeAttribute("aria-selected");
  }
  selectedIndex = i;
  if (i >= 0 && lis[i]) {
    lis[i].classList.add("selected");
    lis[i].setAttribute("aria-selected", "true");
    lis[i].scrollIntoView({ block: "nearest" });
  }
}

document.getElementById("search").addEventListener("input", (e) => search(e.target.value));

document.getElementById("search").addEventListener("focus", (e) => {
  if (e.target.value.trim() === "") showRecent();
});

document.getElementById("search").addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    clearResults();
    return;
  }
  if (!results.length) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    setSelected((selectedIndex + 1) % results.length);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    setSelected(selectedIndex <= 0 ? results.length - 1 : selectedIndex - 1);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (selectedIndex >= 0 && results[selectedIndex]) {
      const entry = results[selectedIndex];
      if (entry.kind === "recent") {
        applyRecent(entry.query);
      } else {
        openResult(entry.item);
      }
    }
  }
});

init();
