let toastTimer;

export function showToast(message) {
  const toast = document.querySelector("#toast");
  // Los diálogos abiertos están en una capa superior a cualquier z-index.
  const dialog = [...document.querySelectorAll("dialog[open]")].at(-1);
  (dialog || document.body).append(toast);
  if (dialog) {
    dialog.addEventListener("close", () => document.body.append(toast), { once: true });
  }
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 5000);
}
