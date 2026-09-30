import { renderIcons } from "./icons.js";

export function showStartupError(error) {
  const screen = document.createElement("section");
  screen.className = "auth-screen";
  const card = document.createElement("div");
  card.className = "auth-card";
  const title = document.createElement("h1");
  title.textContent = "No se pudo cargar el sistema";
  const message = document.createElement("p");
  message.className = "auth-error";
  message.setAttribute("role", "alert");
  message.textContent = error.message || "Comprueba la conexión e intenta nuevamente.";
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "primary wide";
  retry.textContent = "Reintentar";
  retry.addEventListener("click", () => location.reload());
  card.append(title, message, retry);
  screen.append(card);
  document.querySelector("#app-root").replaceChildren(screen);
  retry.focus();
}

const VIEW_FILES = ["dashboard", "inventory", "sales", "movements", "history", "reports", "purchases", "users"];

async function fetchComponent(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`No se pudo cargar ${path}.`);
  return response.text();
}

export async function loadComponents() {
  const root = document.querySelector("#app-root");
  if (!root) throw new Error("No se encontró el contenedor principal.");
  const [layout, dialogs, auth, toast] = await Promise.all([
    fetchComponent("/src/components/layout.html"),
    fetchComponent("/src/components/dialogs.html"),
    fetchComponent("/src/components/auth.html"),
    fetchComponent("/src/components/toast.html"),
  ]);
  root.innerHTML = `${layout}\n${dialogs}\n${auth}\n${toast}`;
  renderIcons(root);
}

export async function loadViews() {
  const container = document.querySelector("#views-container");
  if (!container) throw new Error("No se encontró el contenedor de vistas.");
  const fragments = await Promise.all(VIEW_FILES.map(async (view) => {
    return fetchComponent(`/src/views/${view}.html`);
  }));
  container.innerHTML = fragments.join("\n");
  renderIcons(container);
}
