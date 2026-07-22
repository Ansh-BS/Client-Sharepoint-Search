// Upload form enhancement: drag-drop, client-side validation (early feedback
// only — parse_xlsx on the server stays authoritative), and a submit loading
// state so a slow parse doesn't look frozen. All no-ops if the form is absent
// (i.e. on the preview/result states).
const MAX_BYTES = 10 * 1024 * 1024; // 10 MB

const form = document.querySelector('form[data-role="upload-form"]');
const input = document.getElementById("file");
const zone = document.querySelector(".dropzone");
const info = document.getElementById("file-info");
const submitBtn = form ? form.querySelector('button[type="submit"]') : null;

function humanSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function describe() {
  info.className = "file-info";
  const file = input.files && input.files[0];
  if (!file) { info.textContent = ""; return; }
  if (!/\.xlsx$/i.test(file.name)) {
    info.textContent = "✗ Not an .xlsx file: " + file.name;
    info.classList.add("file-info--bad");
    return;
  }
  if (file.size > MAX_BYTES) {
    info.textContent = "✗ Too large (" + humanSize(file.size) + ", max 10 MB): " + file.name;
    info.classList.add("file-info--bad");
    return;
  }
  info.textContent = "✓ Ready: " + file.name + " (" + humanSize(file.size) + ")";
  info.classList.add("file-info--ok");
}

if (form && input && zone && info) {
  input.addEventListener("change", describe);

  ["dragenter", "dragover"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.add("dropzone--over");
    }));
  ["dragleave", "drop"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.remove("dropzone--over");
    }));
  zone.addEventListener("drop", (e) => {
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) { input.files = files; describe(); }
  });

  form.addEventListener("submit", () => {
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "Working…"; }
  });
}
