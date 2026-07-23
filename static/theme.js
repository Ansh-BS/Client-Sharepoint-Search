// Theme resolution. Loaded synchronously in <head>, before the stylesheet, so
// the class lands before first paint and the page never flashes the wrong
// theme. Deliberately not an inline script: the CSP is script-src 'self', and
// inlining would mean maintaining a nonce or a hash.
(function () {
  var KEY = "theme";

  function stored() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "light" || v === "dark" ? v : null;
    } catch (e) {
      // Storage blocked by policy or private mode. Fall back to the OS.
      return null;
    }
  }

  function prefersDark() {
    return typeof matchMedia === "function" &&
      matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function apply(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }

  function current() {
    return document.documentElement.classList.contains("dark") ? "dark" : "light";
  }

  apply(stored() || (prefersDark() ? "dark" : "light"));

  // The button does not exist yet — <head> runs before <body> is parsed.
  document.addEventListener("DOMContentLoaded", function () {
    var button = document.getElementById("theme-toggle");
    if (!button) return;   // login page has no toggle, by design

    function sync() {
      var dark = current() === "dark";
      button.setAttribute("aria-pressed", String(dark));
      button.textContent = dark ? "Light" : "Dark";
    }

    sync();
    button.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      apply(next);
      try {
        localStorage.setItem(KEY, next);
      } catch (e) {
        // Not persisted; the choice still holds for this page view.
      }
      sync();
    });
  });
})();
