import assert from "node:assert/strict";
import test from "node:test";
import { initializeSidebarNavigation } from "../src/js/ui/navigation.js";

test("el menú lateral se puede contraer, expandir y recordar", (t) => {
  const classes = new Set();
  const values = new Map();
  const attributes = new Map();
  const listeners = new Map();
  const shell = { classList: {
    toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
  } };
  const button = {
    title: "",
    innerHTML: "",
    setAttribute(name, value) { attributes.set(name, value); },
    addEventListener(name, listener) { listeners.set(name, listener); },
  };
  const oldDocument = globalThis.document;
  const oldStorage = globalThis.localStorage;
  globalThis.document = { querySelector: (selector) => selector === "#app-shell" ? shell : button };
  globalThis.localStorage = {
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, value); },
  };
  t.after(() => {
    globalThis.document = oldDocument;
    globalThis.localStorage = oldStorage;
  });

  initializeSidebarNavigation();
  assert.equal(classes.has("sidebar-collapsed"), false);
  assert.equal(attributes.get("aria-expanded"), "true");
  listeners.get("click")();
  assert.equal(classes.has("sidebar-collapsed"), true);
  assert.equal(attributes.get("aria-expanded"), "false");
  assert.equal(values.get("almacen-sidebar-collapsed-v1"), "true");
  listeners.get("click")();
  assert.equal(classes.has("sidebar-collapsed"), false);
  assert.equal(attributes.get("aria-expanded"), "true");
});
