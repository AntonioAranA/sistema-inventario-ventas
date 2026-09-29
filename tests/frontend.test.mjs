import assert from "node:assert/strict";
import test from "node:test";
import { escapeHtml } from "../src/js/utils/formatters.js";
import { renderProducts } from "../src/js/ui/renderers.js";
import { showToast } from "../src/js/ui/notifications.js";
import { apiRequest } from "../src/js/utils/api.js";

test("los textos y atributos no pueden inyectar HTML", () => {
  assert.equal(escapeHtml('<img src="x" onerror=\'attack()\'>&'),
    "&lt;img src=&quot;x&quot; onerror=&#39;attack()&#39;&gt;&amp;");
});

test("la tabla escapa nombres e identificadores de productos", (t) => {
  const elements = {
    "#product-search": { value: "" },
    "#stock-filter": { value: "all" },
    "#products-table": { innerHTML: "" },
    "#products-empty": { classList: { toggle() {} } },
  };
  globalThis.document = { querySelector: (selector) => elements[selector] };
  t.after(() => delete globalThis.document);
  renderProducts([{ id: 'x" onclick="alert(1)', name: "<script>alert(1)</script>", sku: "a", category: "b", price: 0, stock: 0, min: 1 }]);
  const html = elements["#products-table"].innerHTML;
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes('" onclick="'));
  assert.ok(html.includes("&quot; onclick=&quot;"));
});

test("el aviso entra en el diálogo y vuelve a la página al cerrarlo", (t) => {
  let onClose;
  const toast = { classList: { add() {}, remove() {} } };
  const body = { append(node) { node.parent = this; } };
  const dialog = {
    append(node) { node.parent = this; },
    addEventListener(event, callback) { assert.equal(event, "close"); onClose = callback; },
  };
  globalThis.document = {
    body, querySelector: () => toast, querySelectorAll: () => [dialog],
  };
  t.after(() => delete globalThis.document);
  t.mock.method(globalThis, "setTimeout", () => 1);
  t.mock.method(globalThis, "clearTimeout", () => {});
  showToast("Las contraseñas no coinciden");
  assert.equal(toast.parent, dialog);
  assert.equal(toast.textContent, "Las contraseñas no coinciden");
  onClose();
  assert.equal(toast.parent, body);
});

test("la API explica desconexiones y respuestas no JSON", async (t) => {
  const fetchMock = t.mock.method(globalThis, "fetch", async () => { throw new TypeError("fetch failed"); });
  await assert.rejects(apiRequest("/api/state"), /servidor esté iniciado/);
  fetchMock.mock.mockImplementation(async () => new Response("<html>Error</html>", { status: 503 }));
  await assert.rejects(apiRequest("/api/state"), /503/);
});
