import { escapeHtml, formatDate, initials, money } from "../utils/formatters.js";

const element = (selector) => document.querySelector(selector);

export function renderAll(state, cart) {
  renderDashboard(state);
  renderProducts(state.products);
  renderSaleProducts(state.products);
  renderCart(state.products, cart);
  renderHistory(state.sales);
  renderMovements(state.movements || []);
  renderPurchases(state.purchases || [], state.suppliers || []);
}

export function renderDashboard(state) {
  const today = new Date().toDateString();
  const todaySales = state.sales.filter((sale) => new Date(sale.date).toDateString() === today);
  const lowStock = state.products.filter((product) => product.stock <= product.min);
  const stockUnits = state.products.reduce((sum, product) => sum + product.stock, 0);
  const inventoryValue = state.products.reduce((sum, product) => sum + product.stock * product.price, 0);
  const todayTotal = todaySales.reduce((sum, sale) => sum + sale.total, 0);
  const metrics = [
    ["Ventas de hoy", money.format(todayTotal), `${todaySales.length} ventas realizadas`, "💰"],
    ["Productos", state.products.length, `${stockUnits} unidades disponibles`, "📦"],
    ["Por reponer", lowStock.length, lowStock.length ? "Conviene revisarlos" : "Todo está bien", "📋"],
    ["Valor del inventario", money.format(inventoryValue), "Según precio de venta", "🏷️"],
  ];

  element("#metrics").innerHTML = metrics.map(metricTemplate).join("");
  element("#low-stock-list").innerHTML = lowStock.length
    ? lowStock.slice(0, 4).map(lowStockTemplate).join("")
    : '<div class="empty">Todos los productos tienen stock suficiente.</div>';

  const recentSales = [...state.sales].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 4);
  element("#recent-sales").innerHTML = recentSales.length
    ? recentSales.map(recentSaleTemplate).join("")
    : '<div class="empty">Tu próxima venta aparecerá aquí.</div>';
  renderChart(state.sales);
}

export function renderProducts(products) {
  const query = element("#product-search").value.toLowerCase().trim();
  const filter = element("#stock-filter").value;
  const visible = products
    .filter((product) => `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(query))
    .filter((product) => filter === "all" || (filter === "low" ? product.stock <= product.min : product.stock > 0));
  element("#products-table").innerHTML = visible.map(productRowTemplate).join("");
  element("#products-empty").classList.toggle("hidden", visible.length > 0);
}

export function renderSaleProducts(products) {
  const query = element("#sale-search").value.toLowerCase().trim();
  const visible = products.filter((product) => `${product.name} ${product.sku}`.toLowerCase().includes(query));
  element("#sale-products").innerHTML = visible.length
    ? visible.map(saleProductTemplate).join("")
    : '<div class="empty">No hay resultados.</div>';
}

export function renderCart(products, cart) {
  const items = cart
    .map((item) => ({ ...item, product: products.find(({ id }) => id === item.id) }))
    .filter(({ product }) => product);
  element("#cart-items").innerHTML = items.length
    ? items.map(cartItemTemplate).join("")
    : '<div class="cart-empty">Selecciona un producto<br>para comenzar la venta.</div>';
  const total = items.reduce((sum, item) => sum + item.product.price * item.quantity, 0);
  element("#cart-total").textContent = money.format(total);
  element("#complete-sale").disabled = items.length === 0;
}

export function renderHistory(sales) {
  const ordered = [...sales].sort((a, b) => new Date(b.date) - new Date(a.date));
  element("#history-table").innerHTML = ordered.map(historyRowTemplate).join("");
  element("#history-empty").classList.toggle("hidden", ordered.length > 0);
}

export function renderMovements(movements) {
  const query = element("#movement-search").value.toLowerCase().trim();
  const filter = element("#movement-filter").value;
  const visible = movements.filter((movement) => {
    const matchesText = `${movement.productName} ${movement.reason} ${movement.responsible}`.toLowerCase().includes(query);
    const isAdjustment = ["adjustment", "adjustment_in", "adjustment_out", "initial"].includes(movement.type);
    const matchesType = filter === "all" || movement.type === filter || (filter === "entry" && movement.type === "purchase") || (filter === "adjustment" && isAdjustment);
    return matchesText && matchesType;
  });
  element("#movements-table").innerHTML = visible.map(movementRowTemplate).join("");
  element("#movements-empty").classList.toggle("hidden", visible.length > 0);
}

export function renderPurchases(purchases, suppliers) {
  const total = purchases.reduce((sum, purchase) => sum + purchase.total, 0);
  const units = purchases.reduce((sum, purchase) => sum + purchase.items.reduce((itemSum, item) => itemSum + item.quantity, 0), 0);
  const cards = [["Compras registradas", purchases.length, "Recepciones totales", "🚚"], ["Unidades recibidas", units, "Productos ingresados", "📦"], ["Monto comprado", money.format(total), "Costo acumulado", "💳"]];
  element("#purchase-summary").innerHTML = cards.map(metricTemplate).join("");
  const query = element("#purchase-search").value.toLowerCase().trim();
  const days = element("#purchase-period").value;
  const limit = days === "all" ? null : new Date(Date.now() - Number(days) * 86400000);
  const visiblePurchases = purchases.filter((purchase) => {
    const text = `${purchase.folio} ${purchase.supplierName} ${purchase.document}`.toLowerCase();
    return text.includes(query) && (!limit || new Date(purchase.date) >= limit);
  });
  element("#purchases-table").innerHTML = visiblePurchases.map((purchase) => `<tr><td><strong>${purchase.folio}</strong></td><td>${formatDate(purchase.date, true)}</td><td>${escapeHtml(purchase.supplierName)}</td><td>${escapeHtml(purchase.document || "Sin documento")}</td><td><strong>${money.format(purchase.total)}</strong><small>${purchase.items.reduce((sum,item)=>sum+item.quantity,0)} unidades</small></td><td><button class="text-button view-purchase" data-purchase-id="${escapeHtml(purchase.id)}">Ver detalle</button></td></tr>`).join("");
  element("#purchases-empty").classList.toggle("hidden", visiblePurchases.length > 0);

  const supplierQuery = element("#supplier-search").value.toLowerCase().trim();
  const visibleSuppliers = suppliers.filter((supplier) => `${supplier.name} ${supplier.taxId} ${supplier.phone} ${supplier.email}`.toLowerCase().includes(supplierQuery));
  element("#supplier-count").textContent = suppliers.length;
  element("#suppliers-list").innerHTML = visibleSuppliers.length ? visibleSuppliers.map((supplier) => {
    const purchaseCount = purchases.filter((purchase) => purchase.supplierId === supplier.id).length;
    return `<div class="supplier-row"><span class="product-avatar">${escapeHtml(initials(supplier.name))}</span><div><strong>${escapeHtml(supplier.name)}</strong><small>${escapeHtml(supplier.phone || supplier.email || supplier.taxId || "Sin datos de contacto")} · ${purchaseCount} compras</small></div><button class="icon-button edit-supplier" data-supplier-id="${escapeHtml(supplier.id)}" title="Editar">✎</button><button class="icon-button delete-supplier" data-supplier-id="${escapeHtml(supplier.id)}" title="Eliminar">×</button></div>`;
  }).join("") : '<div class="empty">No encontramos proveedores.</div>';
}

function renderChart(sales) {
  const days = [];
  for (let offset = 6; offset >= 0; offset -= 1) {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    start.setDate(start.getDate() - offset);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    const total = sales.filter((sale) => new Date(sale.date) >= start && new Date(sale.date) < end).reduce((sum, sale) => sum + sale.total, 0);
    days.push({ date: start, total });
  }
  const maximum = Math.max(...days.map(({ total }) => total), 1);
  element("#week-total").textContent = money.format(days.reduce((sum, day) => sum + day.total, 0));
  element("#sales-count").textContent = `${sales.filter((sale) => new Date(sale.date) >= days[0].date).length} ventas`;
  element("#sales-chart").innerHTML = days.map((day, index) => chartBarTemplate(day, index, maximum)).join("");
}

function metricTemplate([label, value, detail, icon]) {
  return `<article class="metric"><div class="metric-top"><span>${label}</span><span class="metric-icon">${icon}</span></div><strong>${value}</strong><small>${detail}</small></article>`;
}
function lowStockTemplate(product) {
  return `<div class="attention-item"><span class="product-avatar">${escapeHtml(initials(product.name))}</span><div><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.sku)} · mínimo ${product.min}</small></div><span class="stock-number">${product.stock} uds.</span></div>`;
}
function recentSaleTemplate(sale) {
  const detail = sale.items.map((item) => `${item.quantity}× ${escapeHtml(item.name)}`).join(", ");
  return `<div class="sale-row"><div><strong>${escapeHtml(sale.customer || "Venta mostrador")}</strong><small>${sale.folio}</small></div><div>${detail}</div><strong>${money.format(sale.total)}</strong></div>`;
}
function productRowTemplate(product) {
  const isLow = product.stock <= product.min;
  const status = product.stock === 0 ? "Agotado" : isLow ? "Stock bajo" : "Disponible";
  return `<tr><td><strong>${escapeHtml(product.name)}</strong></td><td>${escapeHtml(product.sku)}</td><td>${escapeHtml(product.category)}</td><td>${money.format(product.price)}</td><td><strong>${product.stock} uds.</strong><small>Mínimo ${product.min}</small></td><td><span class="badge ${isLow ? "low" : ""}">${status}</span></td><td class="row-actions"><button class="icon-button edit-product" data-id="${escapeHtml(product.id)}" title="Editar">✎</button><button class="icon-button delete-button" data-id="${escapeHtml(product.id)}" title="Eliminar">×</button></td></tr>`;
}
function saleProductTemplate(product) {
  return `<button class="product-card" data-add="${escapeHtml(product.id)}" ${product.stock === 0 ? "disabled" : ""}><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.category)}</small><div class="product-card-footer"><b>${money.format(product.price)}</b><span>${product.stock ? `${product.stock} disponibles` : "Agotado"}</span></div></button>`;
}
function cartItemTemplate(item) {
  return `<div class="cart-item"><div><strong>${escapeHtml(item.product.name)}</strong><small>${money.format(item.product.price * item.quantity)}</small></div><div class="quantity"><button data-dec="${escapeHtml(item.id)}">−</button><b>${item.quantity}</b><button data-inc="${escapeHtml(item.id)}">＋</button></div></div>`;
}
function historyRowTemplate(sale) {
  const names = sale.items.map((item) => escapeHtml(item.name)).join(", ");
  const units = sale.items.reduce((sum, item) => sum + item.quantity, 0);
  return `<tr><td><strong>${sale.folio}</strong></td><td>${formatDate(sale.date, true)}</td><td>${escapeHtml(sale.customer || "Venta mostrador")}</td><td>${units} uds.<small>${names}</small></td><td><strong>${money.format(sale.total)}</strong></td></tr>`;
}
function movementRowTemplate(movement) {
  const labels = { initial: "Stock inicial", entry: "Entrada", purchase: "Compra", sale: "Venta", return: "Devolución", loss: "Pérdida", adjustment: "Ajuste", adjustment_in: "Ajuste", adjustment_out: "Ajuste" };
  const sign = movement.quantity > 0 ? "+" : "";
  const quantityClass = movement.quantity > 0 ? "positive" : "negative";
  return `<tr><td>${formatDate(movement.date, true)}</td><td><strong>${escapeHtml(movement.productName)}</strong></td><td><span class="movement-type">${labels[movement.type] || "Movimiento"}</span></td><td><span class="movement-quantity ${quantityClass}">${sign}${movement.quantity}</span></td><td>${escapeHtml(movement.reason)}</td><td>${escapeHtml(movement.responsible)}</td></tr>`;
}
function chartBarTemplate(day, index, maximum) {
  const height = Math.max((day.total / maximum) * 145, 4);
  const weekday = new Intl.DateTimeFormat("es-CL", { weekday: "short" }).format(day.date).replace(".", "");
  return `<div class="bar-wrap"><div class="bar ${index === 6 ? "today" : ""}" style="height:${height}px" title="${money.format(day.total)}"></div><span>${weekday}</span></div>`;
}
