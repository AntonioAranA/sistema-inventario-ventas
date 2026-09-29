import { apiRequest } from "../utils/api.js";

let state = { products: [], sales: [], movements: [], suppliers: [], purchases: [] };

export function getState() { return state; }

export async function initializeStore() {
  state = await request("/api/state");
}

export async function saveProduct(product) {
  await request("/api/products", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(product) });
  await initializeStore();
}

export async function deleteProduct(productId) {
  await request(`/api/products/${encodeURIComponent(productId)}`, { method: "DELETE" });
  await initializeStore();
}

export async function registerSale(payload) {
  const sale = await request("/api/sales", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  await initializeStore();
  return sale;
}

export async function registerMovement(payload) {
  const movement = await request("/api/movements", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  await initializeStore();
  return movement;
}

export async function saveSupplier(payload) {
  await request("/api/suppliers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  await initializeStore();
}

export async function deleteSupplier(id) {
  await request(`/api/suppliers/${encodeURIComponent(id)}`, { method: "DELETE" });
  await initializeStore();
}

export async function registerPurchase(payload) {
  const purchase = await request("/api/purchases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  await initializeStore();
  return purchase;
}

export async function getUsers() { return request("/api/users"); }

export async function saveUser(payload) {
  return request("/api/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

async function request(url, options) {
  try {
    return await apiRequest(url, options);
  } catch (error) {
    if (error.status === 401) location.reload();
    throw error;
  }
}
