import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { icon, renderIcons } from "../src/js/ui/icons.js";
import { renderAll } from "../src/js/ui/renderers.js";

test("todos los iconos de los componentes y vistas existen localmente", () => {
  let count = 0;
  for (const directory of ["../src/components/", "../src/views/"]) {
    const base = new URL(directory, import.meta.url);
    for (const file of readdirSync(base).filter((name) => name.endsWith(".html"))) {
      const html = readFileSync(new URL(file, base), "utf8");
      for (const [, name] of html.matchAll(/data-icon="([^"]+)"/g)) {
        const svg = icon(name);
        assert.match(svg, /<svg /);
        assert.match(svg, /aria-hidden="true"/);
        assert.match(svg, /stroke="currentColor"/);
        count += 1;
      }
    }
  }
  assert.ok(count > 20);
  assert.throws(() => icon("toString"), /desconocido/);
});

test("el cargador inserta SVG decorativos en los componentes", () => {
  const node = { dataset: { icon: "house" }, setAttribute(name, value) { this[name] = value; } };
  renderIcons({ querySelectorAll: () => [node] });
  assert.match(node.innerHTML, /<svg /);
  assert.equal(node["aria-hidden"], "true");
});

test("los iconos siguen presentes al volver a dibujar tablas, carrito y reportes", (t) => {
  const elements = new Map();
  globalThis.document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, {
        value: selector.includes("filter") || selector.includes("period") ? "all" : "",
        innerHTML: "",
        classList: { toggle() {} },
      });
      return elements.get(selector);
    },
  };
  t.after(() => delete globalThis.document);
  const state = {
    products: [{ id: "1", name: "Café", sku: "CAF", category: "Alimentos", stock: 2, min: 3, price: 100 }],
    suppliers: [{ id: "2", name: "Proveedor" }],
    sales: [], purchases: [], movements: [],
  };
  for (let repeat = 0; repeat < 2; repeat += 1) {
    renderAll(state, [{ id: "1", quantity: 1 }]);
    for (const selector of ["#products-table", "#metrics", "#report-metrics", "#purchase-summary", "#stock-alert", "#cart-items", "#suppliers-list"]) {
      assert.match(elements.get(selector).innerHTML, /<svg /, selector);
    }
    assert.match(elements.get("#products-table").innerHTML, /aria-label="Editar"/);
    assert.match(elements.get("#cart-items").innerHTML, /aria-label="Aumentar cantidad"/);
  }
});
