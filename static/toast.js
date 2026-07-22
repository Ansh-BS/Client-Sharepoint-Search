// Transient feedback. Loaded on admin only — the one page that fires toasts
// (success on confirm, info on cancel). Errors are NOT toasts: they render
// inline server-side where they persist. CSP is script-src 'self', so server
// -> toast messages arrive via a hidden #flash element, never an inline script.
const AUTO_DISMISS_MS = 5000;

function container() {
  let el = document.getElementById("toast-container");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast-container";
    el.className = "toast-container";
    el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
  }
  return el;
}

function toast(msg, level = "info") {
  if (!msg) return;
  const node = document.createElement("div");
  node.className = "toast toast--" + level;

  const text = document.createElement("span");
  text.className = "toast__msg";
  text.textContent = msg;
  node.appendChild(text);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "toast__close";
  close.setAttribute("aria-label", "Dismiss");
  close.textContent = "×"; // ×
  node.appendChild(close);

  container().appendChild(node);
  requestAnimationFrame(() => node.classList.add("toast--in"));

  let timer = null;
  const remove = () => {
    node.classList.remove("toast--in");
    node.addEventListener("transitionend", () => node.remove(), { once: true });
    setTimeout(() => node.remove(), 400); // fallback if no transition fires
  };
  const dismiss = () => { if (timer) { clearTimeout(timer); timer = null; } remove(); };
  const arm = () => { timer = setTimeout(dismiss, AUTO_DISMISS_MS); };

  close.addEventListener("click", dismiss);
  node.addEventListener("mouseenter", () => { if (timer) { clearTimeout(timer); timer = null; } });
  node.addEventListener("mouseleave", arm);
  arm();
}
window.toast = toast;

// Source 1: server-rendered success element (present only on the result page).
function readFlash() {
  const el = document.getElementById("flash");
  if (!el) return;
  const msg = el.dataset.msg;
  const level = el.dataset.level || "info";
  el.remove();
  if (msg) toast(msg, level);
}

// Source 2: client one-shot set before navigating (e.g. cancel in modal.js).
function readPending() {
  let raw = null;
  try { raw = sessionStorage.getItem("toast-pending"); } catch (e) { return; }
  if (!raw) return;
  try { sessionStorage.removeItem("toast-pending"); } catch (e) { /* ignore */ }
  try {
    const data = JSON.parse(raw);
    if (data && data.msg) toast(data.msg, data.level || "info");
  } catch (e) { /* malformed, ignore */ }
}

readFlash();
readPending();
