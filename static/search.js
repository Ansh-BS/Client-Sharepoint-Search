let fuse = null;

async function init() {
  const res = await fetch("/api/clients");
  if (res.status === 401) { window.location = "/login"; return; }
  const clients = await res.json();
  fuse = new Fuse(clients, {
    keys: [{ name: "name", weight: 0.7 }, { name: "id", weight: 0.3 }],
    threshold: 0.4,
    ignoreLocation: true,
    useExtendedSearch: true,
  });
  const box = document.getElementById("search");
  box.disabled = false;
  box.focus();
}

function render(results) {
  const list = document.getElementById("results");
  list.innerHTML = "";
  if (!results.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No client found";
    list.appendChild(li);
    return;
  }
  for (const { item } of results.slice(0, 8)) {
    const li = document.createElement("li");
    const info = document.createElement("div");
    info.className = "info";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = item.name;
    const id = document.createElement("span");
    id.className = "cid";
    id.textContent = item.id;
    info.append(name, id);
    li.appendChild(info);
    if (item.link) {
      const a = document.createElement("a");
      a.href = item.link;
      a.target = "_blank";
      a.rel = "noopener";
      a.className = "open";
      a.textContent = "Open folder";
      li.appendChild(a);
    } else {
      const badge = document.createElement("span");
      badge.className = "nolink";
      badge.textContent = "No link on file";
      li.appendChild(badge);
    }
    list.appendChild(li);
  }
}

document.getElementById("search").addEventListener("input", (e) => {
  const q = e.target.value.trim();
  if (q.length < 2 || !fuse) {
    document.getElementById("results").innerHTML = "";
    return;
  }
  render(fuse.search(q));
});

init();
