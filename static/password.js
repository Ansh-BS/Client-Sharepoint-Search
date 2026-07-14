// Password reveal. Wired here rather than inline because the CSP is
// script-src 'self' — an onclick attribute would be dropped silently.
//
// The button is the control, not the input: it carries aria-pressed so the
// current state is announced, and its label says what the next press does.
for (const button of document.querySelectorAll(".reveal")) {
  const input = document.getElementById(button.dataset.for);
  if (!input) continue;

  button.addEventListener("click", () => {
    const shown = input.type === "text";
    input.type = shown ? "password" : "text";
    button.setAttribute("aria-pressed", String(!shown));
    button.setAttribute("aria-label", shown ? "Show password" : "Hide password");
    // The press moves focus to the button; put the caret back where it was so
    // the user can keep typing without reaching for the mouse again.
    const caret = input.value.length;
    input.focus();
    input.setSelectionRange(caret, caret);
  });
}
