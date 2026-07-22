// Preview modal. The server renders the review card as <dialog open> so it
// works with JS off (an in-flow card). Here we upgrade it to a true modal:
// drop `open`, call showModal() for focus-trap, backdrop, and Esc handling.
//
// In the preview state the dialog is the ONLY thing on the page (the upload
// form is not rendered). So closing must not just hide the dialog — that would
// reveal a blank page. Esc and backdrop clicks route through the server cancel
// form, which navigates back to the upload form.
const dialog = document.getElementById("preview-modal");

function queueCancelToast() {
  try {
    sessionStorage.setItem("toast-pending",
      JSON.stringify({ msg: "Upload cancelled — nothing was changed.", level: "info" }));
  } catch (e) { /* storage disabled: skip the toast, cancel still works */ }
}

if (dialog && typeof dialog.showModal === "function") {
  const cancelForm = dialog.querySelector('form[data-role="cancel-form"]');
  const cancelBtn = dialog.querySelector('[data-role="cancel"]');

  dialog.removeAttribute("open");
  dialog.showModal();

  // Safe default focus: Cancel, not the destructive Replace.
  if (cancelBtn) cancelBtn.focus();

  function doCancel() {
    queueCancelToast();
    if (cancelForm) cancelForm.submit(); // navigates; dialog stays until then
  }

  // Cancel button submits its own form; just queue the toast alongside it.
  if (cancelForm) cancelForm.addEventListener("submit", queueCancelToast);

  // Esc fires the dialog 'cancel' event. Prevent the instant close (blank page)
  // and route through the server cancel instead.
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); doCancel(); });

  // Backdrop click = a click that lands outside the dialog's box. Testing
  // e.target === dialog alone would also fire on clicks in the dialog's own
  // padding band (inside the visible modal), cancelling by accident; gate on
  // the pointer being outside the box instead.
  dialog.addEventListener("click", (e) => {
    if (e.target !== dialog) return; // click was on inner content
    const r = dialog.getBoundingClientRect();
    const outside = e.clientX < r.left || e.clientX > r.right ||
                    e.clientY < r.top || e.clientY > r.bottom;
    if (outside) doCancel();
  });
}
