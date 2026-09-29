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
}

export async function loadViews() {
  const container = document.querySelector("#views-container");
  if (!container) throw new Error("No se encontró el contenedor de vistas.");
  const fragments = await Promise.all(VIEW_FILES.map(async (view) => {
    return fetchComponent(`/src/views/${view}.html`);
  }));
  container.innerHTML = fragments.join("\n");
}
