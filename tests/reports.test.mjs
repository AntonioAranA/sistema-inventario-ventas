import assert from "node:assert/strict";
import test from "node:test";
import { inventoryCostLookup, summarizeProfit } from "../src/js/utils/reports.js";
import { csvRows, parseBackup } from "../src/js/utils/exports.js";
import { showStartupError, loadComponents } from "../src/js/ui/views.js";
import { initializeAuth } from "../src/js/auth.js";
import { renderReports } from "../src/js/ui/renderers.js";

const purchase = (date, items) => ({ date, items });
const item = (productId, quantity, unitCost) => ({ productId, quantity, unitCost });

test("el promedio móvil descuenta ventas y recalcula con cada compra", () => {
  const costFor = inventoryCostLookup({
    purchases: [
      purchase("2026-01-01T12:00:00Z", [item("a", 2, 100)]),
      purchase("2026-01-03T12:00:00Z", [item("a", 2, 200)]),
    ],
    sales: [
      { id: "s1", date: "2026-01-02T12:00:00Z", items: [{ id: "a", quantity: 1 }] },
      { id: "s2", date: "2026-01-04T12:00:00Z", items: [{ id: "a", quantity: 1 }] },
    ],
  });
  assert.equal(costFor("a", "2026-01-02T12:00:00Z", "s1"), 100);
  assert.equal(costFor("a", "2026-01-04T12:00:00Z", "s2"), 500 / 3);
  assert.equal(costFor("missing", "2026-01-04T12:00:00Z", "missing"), null);
});

test("el stock inicial sin costo se mantiene desconocido hasta agotarse", () => {
  const costFor = inventoryCostLookup({
    purchases: [purchase("2026-01-02T12:00:00Z", [item("a", 2, 100)])],
    sales: [
      { id: "s1", date: "2026-01-03T12:00:00Z", items: [{ id: "a", quantity: 1 }] },
      { id: "s2", date: "2026-01-04T12:00:00Z", items: [{ id: "a", quantity: 2 }] },
      { id: "s3", date: "2026-01-05T12:00:00Z", items: [{ id: "a", quantity: 1 }] },
    ],
    movements: [{ productId: "a", type: "initial", quantity: 2, date: "2026-01-01T12:00:00Z" }],
  });
  assert.equal(costFor("a", "2026-01-03T12:00:00Z", "s1"), null);
  assert.equal(costFor("a", "2026-01-04T12:00:00Z", "s2"), null);
  assert.equal(costFor("a", "2026-01-05T12:00:00Z", "s3"), 100);
});

test("el reporte distingue costos desconocidos, pérdidas y productos homónimos", () => {
  const sales = [{ date: "2026-01-02T12:00:00Z", items: [
    { id: "a", name: "Producto", price: 100, quantity: 2 },
    { id: "b", name: "Producto", price: 500, quantity: 3 },
  ] }];
  const profit = summarizeProfit(sales, (id) => id === "a" ? 120 : null);
  assert.equal(profit.profit, -40);
  assert.equal(profit.missingUnits, 3);
  assert.equal(profit.knownUnits, 2);
  assert.equal(profit.products.length, 2);
});

test("los CSV escapan separadores, comillas y fórmulas sin alterar números negativos", () => {
  const csv = csvRows([['Café; "Especial"', "=1+1", "  @SUM(A1)", -20, "línea\nnueva"]]);
  assert.equal(csv, '"Café; ""Especial""";"\'=1+1";"\'  @SUM(A1)";"-20";"línea\nnueva"');
});

test("los respaldos antiguos con BOM se leen y se rechazan archivos incompletos", () => {
  const data = { products: [], suppliers: [], sales: [], purchases: [], movements: [] };
  assert.deepEqual(parseBackup("\uFEFF" + JSON.stringify(data)), data);
  for (const source of ["null", "[]", '{"products":[]}']) {
    assert.throws(() => parseBackup(source), /completo/);
  }
});

test("si falla un componente se muestra un error sin depender del formulario de acceso", async (t) => {
  let screen;
  const root = { replaceChildren(node) { screen = node; } };
  globalThis.document = {
    querySelector: () => root,
    createElement: () => ({
      children: [], append(...nodes) { this.children.push(...nodes); },
      setAttribute() {}, addEventListener() {}, focus() { this.focused = true; },
    }),
  };
  t.after(() => delete globalThis.document);
  t.mock.method(globalThis, "fetch", async () => new Response("", { status: 404 }));
  await assert.rejects(loadComponents(), /No se pudo cargar/);
  showStartupError(new Error("Archivo no disponible"));
  const card = screen.children[0];
  assert.equal(card.children[1].textContent, "Archivo no disponible");
  assert.equal(card.children[2].textContent, "Reintentar");
  assert.equal(card.children[2].focused, true);
});

test("el vendedor no recibe una ganancia ficticia al no tener acceso a compras", async (t) => {
  const elements = new Map();
  globalThis.document = { querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, { value: "all", classList: { add() {}, remove() {}, toggle() {} } });
    return elements.get(selector);
  } };
  t.after(() => delete globalThis.document);
  t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ authenticated: true, user: { role: "seller" } })));
  await initializeAuth();
  renderReports({ products: [], purchases: [], sales: [{ total: 100, date: new Date().toISOString(), items: [{ id: "a", name: "A", quantity: 1, price: 100 }] }] });
  assert.doesNotMatch(elements.get("#report-metrics").innerHTML, /Ganancia/);
  assert.doesNotMatch(elements.get("#top-products-table").innerHTML, /Ganancia/);
  assert.equal(elements.get("#profit-note").hidden, true);
});
