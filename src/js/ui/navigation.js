import { icon } from "./icons.js";

const STORAGE_KEY = "almacen-sidebar-collapsed-v1";

export function initializeSidebarNavigation() {
  const shell = document.querySelector("#app-shell");
  const button = document.querySelector("#sidebar-toggle");
  let collapsed = false;

  try {
    collapsed = localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    // Keep the sidebar expanded if browser storage is unavailable.
  }

  const update = () => {
    shell.classList.toggle("sidebar-collapsed", collapsed);
    button.setAttribute("aria-expanded", String(!collapsed));
    const action = collapsed ? "Expandir menú" : "Contraer menú";
    button.setAttribute("aria-label", action);
    button.title = action;
    button.innerHTML = `${icon(collapsed ? "panel-left-open" : "panel-left-close")}<span class="sidebar-toggle-label">${action}</span>`;
  };

  button.addEventListener("click", () => {
    collapsed = !collapsed;
    update();
    try {
      localStorage.setItem(STORAGE_KEY, String(collapsed));
    } catch {
      // The current session still keeps the chosen layout.
    }
  });

  update();
}
