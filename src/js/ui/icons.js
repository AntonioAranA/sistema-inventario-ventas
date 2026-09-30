import { icons } from "../vendor/lucide.js";

// Decorative icons: the surrounding text or button provides the accessible name.
export function icon(name) {
  if (!Object.hasOwn(icons, name)) throw new Error(`Icono desconocido: ${name}`);
  return `<svg class="icon" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${icons[name]}</svg>`;
}

export function renderIcons(root) {
  root.querySelectorAll("[data-icon]").forEach((node) => {
    node.innerHTML = icon(node.dataset.icon);
    node.setAttribute("aria-hidden", "true");
  });
}
