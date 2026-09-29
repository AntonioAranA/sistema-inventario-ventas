import { VALID_VIEWS, VIEW_TITLES } from "./config.js";
import { deleteProduct, deleteSupplier, getState, getUsers, initializeStore, registerMovement, registerPurchase, registerSale, saveProduct, saveSupplier, saveUser } from "./data/store.js";
import { escapeHtml, formatDate, money } from "./utils/formatters.js";
import { changePassword, getCurrentUser, initializeAuth, logout } from "./auth.js";
import { showToast } from "./ui/notifications.js";
import { initializeAccessibility } from "./ui/accessibility.js";
import { loadComponents, loadViews } from "./ui/views.js";
import { renderAll, renderCart, renderMovements, renderProducts, renderReports, renderSaleProducts } from "./ui/renderers.js";

let cart = [];
let purchaseItems = [];
let users = [];
let salePending = false;
let currentUser = null;
const element = (selector) => document.querySelector(selector);
const refresh = () => renderAll(getState(), cart);

function downloadFile(filename, content, type = "text/csv;charset=utf-8") {
  const blob = new Blob(["\uFEFF", content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.append(link);
  link.click();
  setTimeout(() => { link.remove(); URL.revokeObjectURL(url); }, 1000);
}

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function csvRows(rows) {
  // El punto y coma funciona mejor con Excel configurado en español.
  return rows.map((row) => row.map(csvCell).join(";")).join("\r\n");
}

function exportSales() {
  const period = element("#report-period").value;
  const limit = period === "all" ? null : new Date(Date.now() - Number(period) * 86400000);
  const rows = [["Folio", "Fecha", "Cliente", "Producto", "SKU", "Cantidad", "Precio unitario", "Subtotal"]];
  const state = getState();
  [...state.sales].filter((sale) => !limit || new Date(sale.date) >= limit).sort((a, b) => new Date(a.date) - new Date(b.date)).forEach((sale) => sale.items.forEach((item) => {
    const product = state.products.find(({ id }) => id === item.id || id === item.productId);
    rows.push([sale.folio, formatDate(sale.date, true), sale.customer || "Venta mostrador", item.name, product?.sku || "", item.quantity, item.price, item.price * item.quantity]);
  }));
  downloadFile(`ventas-${new Date().toISOString().slice(0, 10)}.csv`, csvRows(rows));
  showToast("Reporte de ventas descargado");
}

function exportInventory() {
  const rows = [["Producto", "SKU", "Categoría", "Precio de venta", "Stock actual", "Stock mínimo", "Diferencia", "Estado"]];
  [...getState().products].sort((a, b) => `${a.category}${a.name}`.localeCompare(`${b.category}${b.name}`, "es")).forEach((product) => rows.push([product.name, product.sku, product.category, product.price, product.stock, product.min, product.stock - product.min, product.stock <= product.min ? "Stock bajo" : "Disponible"]));
  downloadFile(`inventario-${new Date().toISOString().slice(0, 10)}.csv`, csvRows(rows));
  showToast("Reporte de inventario descargado");
}

function exportBackup() {
  downloadFile(`respaldo-inventario-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify({ exportedAt: new Date().toISOString(), ...getState() }, null, 2), "application/json;charset=utf-8");
  showToast("Respaldo descargado");
}

function navigate(view) {
  const role = getCurrentUser()?.role;
  const forbidden = role === "seller" ? ["movements", "purchases", "users"] : role === "inventory" ? ["sales", "users"] : [];
  if (!VALID_VIEWS.includes(view) || forbidden.includes(view)) view = "dashboard";
  document.querySelectorAll(".view").forEach((section) => section.classList.toggle("active", section.id === `${view}-view`));
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  element("#page-title").textContent = VIEW_TITLES[view];
  location.hash = view;
  window.scrollTo({ top: 0, behavior: document.documentElement.classList.contains("reduced-motion") ? "instant" : "smooth" });
  refresh();
}

function openProductModal(productId) {
  const product = getState().products.find(({ id }) => id === productId);
  element("#product-form").reset();
  element("#modal-title").textContent = product ? "Editar producto" : "Nuevo producto";
  element("#product-id").value = product?.id || "";
  element("#product-name").value = product?.name || "";
  element("#product-sku").value = product?.sku || "";
  element("#product-category").value = product?.category || "";
  element("#product-price").value = product?.price ?? "";
  element("#product-min").value = product?.min ?? 5;
  element("#product-modal").showModal();
}

function openMovementModal() {
  fillSelect("#movement-product", getState().products, (product) => `${product.name} · ${product.stock} disponibles`);
  element("#movement-form").reset();
  element("#movement-quantity").value = 1;
  element("#movement-modal").showModal();
}

function openSupplierModal(supplierId) {
  const supplier = getState().suppliers.find(({ id }) => id === supplierId);
  element("#supplier-form").reset();
  element("#supplier-modal-title").textContent = supplier ? "Editar proveedor" : "Nuevo proveedor";
  element("#supplier-id").value = supplier?.id || "";
  element("#supplier-name").value = supplier?.name || "";
  element("#supplier-tax-id").value = supplier?.taxId || "";
  element("#supplier-phone").value = supplier?.phone || "";
  element("#supplier-email").value = supplier?.email || "";
  element("#supplier-modal").showModal();
}

function openPurchaseModal() {
  if (!getState().suppliers.length) {
    showToast("Primero agrega un proveedor");
    openSupplierModal();
    return;
  }
  fillSelect("#purchase-supplier", getState().suppliers, (item) => item.name);
  fillSelect("#purchase-product", getState().products, (item) => `${item.name} · stock ${item.stock}`);
  element("#purchase-form").reset();
  purchaseItems = [];
  renderPurchaseDraft();
  element("#purchase-modal").showModal();
}

function fillSelect(selector, items, label) {
  const select = element(selector);
  select.replaceChildren(...items.map((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = label(item);
    return option;
  }));
}

function addPurchaseItem() {
  const productId = element("#purchase-product").value;
  const quantity = Number(element("#purchase-quantity").value);
  const unitCost = Number(element("#purchase-cost").value);
  const product = getState().products.find(({ id }) => id === productId);
  if (!product || !Number.isSafeInteger(quantity) || !Number.isSafeInteger(unitCost) || quantity < 1 || unitCost < 0) return showToast("Revisa cantidad y costo: deben ser números enteros");
  const existing = purchaseItems.find((item) => item.productId === productId && item.unitCost === unitCost);
  if (existing) { existing.quantity += quantity; }
  else purchaseItems.push({ productId, productName: product.name, quantity, unitCost });
  renderPurchaseDraft();
}

function renderPurchaseDraft() {
  element("#purchase-items").innerHTML = purchaseItems.length ? purchaseItems.map((item, index) => `<div class="purchase-item"><div><strong>${escapeHtml(item.productName)}</strong><small>${item.quantity} × ${money.format(item.unitCost)}</small></div><strong>${money.format(item.quantity * item.unitCost)}</strong><button type="button" class="icon-button remove-purchase-item" data-index="${index}">×</button></div>`).join("") : '<div class="cart-empty">Agrega los productos recibidos.</div>';
  element("#purchase-total").textContent = money.format(purchaseItems.reduce((sum, item) => sum + item.quantity * item.unitCost, 0));
}

async function submitSupplier() {
  try {
    await saveSupplier({ id: element("#supplier-id").value || undefined, name: element("#supplier-name").value.trim(), taxId: element("#supplier-tax-id").value.trim(), phone: element("#supplier-phone").value.trim(), email: element("#supplier-email").value.trim() });
    refresh();
    switchSupplyTab("suppliers");
    showToast(element("#supplier-id").value ? "Proveedor actualizado" : "Proveedor guardado");
    return true;
  } catch (error) { showToast(error.message); return false; }
}

function openPurchaseDetail(purchaseId) {
  const purchase = getState().purchases.find(({ id }) => id === purchaseId);
  if (!purchase) return;
  element("#purchase-detail-title").textContent = purchase.folio;
  element("#purchase-detail-content").innerHTML = `<div class="purchase-detail-meta"><div><small>Proveedor</small><strong>${escapeHtml(purchase.supplierName)}</strong></div><div><small>Documento</small><strong>${escapeHtml(purchase.document || "Sin documento")}</strong></div><div><small>Responsable</small><strong>${escapeHtml(purchase.responsible)}</strong></div><div><small>Fecha</small><strong>${formatDate(purchase.date, true)}</strong></div></div><div>${purchase.items.map((item) => `<div class="detail-item"><div><strong>${escapeHtml(item.productName)}</strong><small>${item.quantity} × ${money.format(item.unitCost)}</small></div><strong>${money.format(item.quantity * item.unitCost)}</strong></div>`).join("")}</div>${purchase.notes ? `<p class="purchase-detail-notes"><strong>Notas:</strong> ${escapeHtml(purchase.notes)}</p>` : ""}<div class="purchase-total"><span>Total</span><strong>${money.format(purchase.total)}</strong></div>`;
  element("#purchase-detail-modal").showModal();
}

async function submitPurchase() {
  if (!purchaseItems.length) { showToast("Agrega al menos un producto"); return false; }
  try {
    const purchase = await registerPurchase({ supplierId: element("#purchase-supplier").value, document: element("#purchase-document").value.trim(), notes: element("#purchase-notes").value.trim(), items: purchaseItems });
    purchaseItems = []; refresh(); showToast(`Compra ${purchase.folio} recibida`); return true;
  } catch (error) { showToast(error.message); return false; }
}

async function submitMovement() {
  try {
    await registerMovement({
      productId: element("#movement-product").value,
      type: element("#movement-type").value,
      quantity: Number(element("#movement-quantity").value),
      reason: element("#movement-reason").value.trim(),
    });
    refresh();
    showToast("Movimiento registrado");
    return true;
  } catch (error) {
    showToast(error.message);
    return false;
  }
}

async function submitProduct() {
  const id = element("#product-id").value;
  const sku = element("#product-sku").value.trim();
  const duplicate = getState().products.some((product) => product.sku.toLowerCase() === sku.toLowerCase() && product.id !== id);
  if (duplicate) {
    showToast("Ese SKU ya está en uso");
    return false;
  }
  try {
    await saveProduct({
      id: id || crypto.randomUUID(),
      name: element("#product-name").value.trim(),
      sku,
      category: element("#product-category").value.trim(),
      price: Number(element("#product-price").value),
      min: Number(element("#product-min").value),
    });
    refresh();
    showToast(id ? "Producto actualizado" : "Producto agregado");
    return true;
  } catch (error) {
    showToast(error.message);
    return false;
  }
}

function switchSupplyTab(tab) {
  document.querySelectorAll(".supply-tab").forEach((button) => {
    const active = button.dataset.supplyTab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".supply-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `supply-${tab}`);
  });
}

function applyPermissions(user) {
  const isAdmin = user.role === "admin";
  const canSell = isAdmin || user.role === "seller";
  const canManageStock = isAdmin || user.role === "inventory";
  document.documentElement.dataset.role = user.role;
  document.querySelectorAll(".admin-only").forEach((item) => item.hidden = !isAdmin);
  document.querySelectorAll('[data-view="sales"]').forEach((item) => item.hidden = !canSell);
  document.querySelectorAll('[data-view="movements"], [data-view="purchases"]').forEach((item) => item.hidden = !canManageStock);
  element("#quick-sale").hidden = !canSell;
  element("#add-product").hidden = !canManageStock;
  element("#add-movement").hidden = !canManageStock;
  element("#add-supplier").hidden = !canManageStock;
  element("#add-purchase").hidden = !canManageStock;
  element("#current-user").textContent = `${user.name} · ${roleLabel(user.role)}`;
}

const roleLabel = (role) => ({ admin: "Administrador", seller: "Vendedor", inventory: "Inventario" }[role] || role);

async function loadUsers() {
  users = await getUsers();
  const activeAdmins = users.filter((user) => user.active && user.role === "admin").length;
  element("#users-table").innerHTML = users.map((user) => {
    const protectedAccount = user.id === currentUser.id || (user.active && user.role === "admin" && activeAdmins === 1);
    const action = protectedAccount
      ? `<span class="protected-user">${user.id === currentUser.id ? "Tu cuenta" : "Administrador requerido"}</span>`
      : `<button class="text-button toggle-user" data-user-id="${escapeHtml(user.id)}">${user.active ? "Desactivar" : "Activar"}</button>`;
    return `<tr><td><strong>${escapeHtml(user.name)}</strong></td><td>${escapeHtml(user.username)}</td><td><span class="badge">${roleLabel(user.role)}</span></td><td><span class="${user.active ? "status-active" : "status-inactive"}">${user.active ? "Activo" : "Inactivo"}</span></td><td class="row-actions">${action}</td></tr>`;
  }).join("");
}

function updateRoleDescription() {
  const descriptions = { admin: "Acceso completo, usuarios y configuración.", seller: "Puede registrar ventas y consultar información.", inventory: "Puede gestionar productos, movimientos y abastecimiento." };
  element("#role-description").textContent = descriptions[element("#user-role").value];
}

function openAccountModal(user) {
  element("#account-name").textContent = user.name;
  element("#account-role").textContent = `${roleLabel(user.role)} · ${user.username}`;
  element("#password-form").reset();
  element("#account-modal").showModal();
}

async function submitPasswordChange() {
  const password = element("#new-password").value;
  if (password !== element("#confirm-password").value) {
    showToast("Las contraseñas nuevas no coinciden");
    return false;
  }
  try {
    await changePassword(element("#current-password").value, password);
    showToast("Contraseña actualizada");
    return true;
  } catch (error) { showToast(error.message); return false; }
}

async function submitUser() {
  try {
    await saveUser({ name: element("#user-name").value.trim(), username: element("#user-username").value.trim(), password: element("#user-password").value, role: element("#user-role").value });
    await loadUsers(); showToast("Usuario creado"); return true;
  } catch (error) { showToast(error.message); return false; }
}

function addToCart(productId) {
  const product = getState().products.find(({ id }) => id === productId);
  const item = cart.find(({ id }) => id === productId);
  if (!product || (item?.quantity || 0) >= product.stock) {
    showToast("No hay más unidades disponibles");
    return;
  }
  if (item) item.quantity += 1;
  else cart.push({ id: productId, quantity: 1 });
  renderCart(getState().products, cart);
}

function changeQuantity(productId, amount) {
  const item = cart.find(({ id }) => id === productId);
  if (!item) return;
  if (amount > 0) return addToCart(productId);
  item.quantity += amount;
  if (item.quantity <= 0) cart = cart.filter(({ id }) => id !== productId);
  renderCart(getState().products, cart);
}

async function completeSale() {
  if (!cart.length || salePending) return;
  salePending = true;
  element("#complete-sale").disabled = true;
  try {
    const items = cart.map((cartItem) => {
      const product = getState().products.find(({ id }) => id === cartItem.id);
      if (!product) throw new Error("Un producto del carrito ya no está disponible");
      return { id: product.id, name: product.name, price: product.price, quantity: cartItem.quantity };
    });
    const sale = await registerSale({ customer: element("#customer-name").value.trim(), items });
    cart = [];
    element("#customer-name").value = "";
    showToast(`Venta ${sale.folio} registrada`);
    navigate("dashboard");
  } catch (error) {
    showToast(error.message);
    refresh();
  } finally {
    salePending = false;
    element("#complete-sale").disabled = !cart.length;
  }
}

async function handleDocumentClick(event) {
  const go = event.target.closest("[data-go]");
  const edit = event.target.closest(".edit-product");
  const remove = event.target.closest(".delete-button");
  const add = event.target.closest("[data-add]");
  const increment = event.target.closest("[data-inc]");
  const decrement = event.target.closest("[data-dec]");
  const removeSupplier = event.target.closest(".delete-supplier");
  const removePurchaseItem = event.target.closest(".remove-purchase-item");
  const editSupplier = event.target.closest(".edit-supplier");
  const viewPurchase = event.target.closest(".view-purchase");
  const toggleUser = event.target.closest(".toggle-user");
  if (go) navigate(go.dataset.go);
  if (edit) openProductModal(edit.dataset.id);
  if (add) addToCart(add.dataset.add);
  if (increment) changeQuantity(increment.dataset.inc, 1);
  if (decrement) changeQuantity(decrement.dataset.dec, -1);
  if (removePurchaseItem) { purchaseItems.splice(Number(removePurchaseItem.dataset.index), 1); renderPurchaseDraft(); }
  if (editSupplier) openSupplierModal(editSupplier.dataset.supplierId);
  if (viewPurchase) openPurchaseDetail(viewPurchase.dataset.purchaseId);
  if (toggleUser) {
    const user = users.find(({ id }) => id === toggleUser.dataset.userId);
    try { await saveUser({ id: user.id, name: user.name, role: user.role, active: !user.active }); await loadUsers(); showToast("Usuario actualizado"); }
    catch (error) { showToast(error.message); }
  }
  if (removeSupplier && confirm("¿Eliminar este proveedor?")) {
    try { await deleteSupplier(removeSupplier.dataset.supplierId); refresh(); showToast("Proveedor eliminado"); }
    catch (error) { showToast(error.message); }
  }
  if (remove && confirm("¿Eliminar este producto del inventario?")) {
    try {
      await deleteProduct(remove.dataset.id);
      cart = cart.filter(({ id }) => id !== remove.dataset.id);
      refresh();
      showToast("Producto eliminado");
    } catch (error) {
      showToast(error.message);
    }
  }
}

function bindEvents() {
  window.addEventListener("hashchange", () => navigate(location.hash.slice(1)));
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.view)));
  document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => element("#product-modal").close()));
  document.querySelectorAll("[data-close-movement]").forEach((button) => button.addEventListener("click", () => element("#movement-modal").close()));
  document.querySelectorAll("[data-close-supplier]").forEach((button) => button.addEventListener("click", () => element("#supplier-modal").close()));
  document.querySelectorAll("[data-close-purchase]").forEach((button) => button.addEventListener("click", () => element("#purchase-modal").close()));
  document.querySelectorAll("[data-close-purchase-detail]").forEach((button) => button.addEventListener("click", () => element("#purchase-detail-modal").close()));
  document.querySelectorAll("[data-supply-tab]").forEach((button) => button.addEventListener("click", () => switchSupplyTab(button.dataset.supplyTab)));
  element("#quick-sale").addEventListener("click", () => navigate("sales"));
  element("#add-product").addEventListener("click", () => openProductModal());
  element("#add-movement").addEventListener("click", openMovementModal);
  element("#add-supplier").addEventListener("click", () => openSupplierModal());
  element("#add-purchase").addEventListener("click", openPurchaseModal);
  element("#add-purchase-item").addEventListener("click", addPurchaseItem);
  element("#add-user").addEventListener("click", () => { element("#user-form").reset(); updateRoleDescription(); element("#user-modal").showModal(); });
  document.querySelectorAll("[data-close-user]").forEach((button) => button.addEventListener("click", () => element("#user-modal").close()));
  element("#user-role").addEventListener("change", updateRoleDescription);
  element("#current-user").addEventListener("click", () => openAccountModal(currentUser));
  document.querySelectorAll("[data-close-account]").forEach((button) => button.addEventListener("click", () => element("#account-modal").close()));
  element("#logout-button").addEventListener("click", () => logout().catch((error) => showToast(error.message)));
  element("#purchase-search").addEventListener("input", refresh);
  element("#purchase-period").addEventListener("change", refresh);
  element("#supplier-search").addEventListener("input", refresh);
  element("#product-search").addEventListener("input", () => renderProducts(getState().products));
  element("#stock-filter").addEventListener("change", () => renderProducts(getState().products));
  element("#sale-search").addEventListener("input", () => renderSaleProducts(getState().products));
  element("#movement-search").addEventListener("input", () => renderMovements(getState().movements));
  element("#movement-filter").addEventListener("change", () => renderMovements(getState().movements));
  element("#report-period").addEventListener("change", () => renderReports(getState()));
  element("#export-sales").addEventListener("click", exportSales);
  element("#export-inventory").addEventListener("click", exportInventory);
  element("#export-all").addEventListener("click", exportBackup);
  element("#clear-cart").addEventListener("click", () => { cart = []; renderCart(getState().products, cart); });
  element("#complete-sale").addEventListener("click", completeSale);
  for (const [name, submit, modal] of [
    ["product", submitProduct, "product"], ["movement", submitMovement, "movement"],
    ["supplier", submitSupplier, "supplier"], ["purchase", submitPurchase, "purchase"],
    ["user", submitUser, "user"], ["password", submitPasswordChange, "account"],
  ]) {
    const form = element(`#${name}-form`);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.getAttribute("aria-busy") === "true") return;
      form.setAttribute("aria-busy", "true");
      const button = form.querySelector('button[value="save"]');
      button.disabled = true;
      try {
        if (await submit()) element(`#${modal}-modal`).close();
      } finally {
        form.removeAttribute("aria-busy");
        button.disabled = false;
      }
    });
  }
  document.addEventListener("click", handleDocumentClick);
}

async function startApp() {
  try {
    await loadComponents();
    await loadViews();
    element("#today").textContent = formatDate(new Date());
    initializeAccessibility();
    currentUser = await initializeAuth();
    applyPermissions(currentUser);
    await initializeStore();
    if (currentUser.role === "admin") await loadUsers();
    bindEvents();
    navigate(location.hash.slice(1));
  } catch (error) {
    element("#auth-screen").classList.remove("hidden");
    element("#auth-title").textContent = "No se pudo cargar el sistema";
    element("#auth-error").textContent = error.message;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "primary wide";
    retry.textContent = "Reintentar";
    retry.addEventListener("click", () => location.reload());
    element("#auth-form").replaceChildren(element("#auth-title"), element("#auth-error"), retry);
  }
}

startApp();
