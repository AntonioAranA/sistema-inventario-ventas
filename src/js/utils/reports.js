// Rebuilds the moving average from dated stock events. Stock with no recorded
// purchase cost remains unknown until it has been fully removed from inventory.
export function inventoryCostLookup({ purchases = [], sales = [], movements = [] }) {
  const events = new Map();
  const add = (id, event) => {
    const rows = events.get(id) || [];
    rows.push(event);
    events.set(id, rows);
  };
  for (const purchase of purchases) {
    for (const item of purchase.items) {
      add(item.productId, { date: new Date(purchase.date).getTime(), type: "purchase", quantity: item.quantity, cost: item.unitCost });
    }
  }
  for (const sale of sales) {
    for (const item of sale.items) {
      add(item.id, { date: new Date(sale.date).getTime(), type: "sale", quantity: item.quantity, saleId: sale.id });
    }
  }
  for (const movement of movements) {
    // Purchases and sales already carry unit-level details above.
    if (movement.type === "purchase" || movement.type === "sale") continue;
    add(movement.productId, { date: new Date(movement.date).getTime(), type: "movement", quantity: movement.quantity });
  }

  const saleCosts = new Map();
  for (const [productId, rows] of events) {
    rows.sort((a, b) => a.date - b.date || eventOrder(a) - eventOrder(b));
    let knownQuantity = 0;
    let knownValue = 0;
    let unknownQuantity = 0;
    for (const row of rows) {
      if (row.type === "purchase") {
        knownQuantity += row.quantity;
        knownValue += row.quantity * row.cost;
        continue;
      }
      if (row.type === "sale") {
        const cost = unknownQuantity === 0 && knownQuantity >= row.quantity && knownQuantity > 0
          ? knownValue / knownQuantity
          : null;
        saleCosts.set(`${row.saleId}:${productId}`, cost);
        const unknownUsed = Math.min(unknownQuantity, row.quantity);
        unknownQuantity -= unknownUsed;
        const knownUsed = Math.min(knownQuantity, row.quantity - unknownUsed);
        const average = knownQuantity ? knownValue / knownQuantity : 0;
        knownQuantity -= knownUsed;
        knownValue = Math.max(0, knownValue - average * knownUsed);
        continue;
      }
      if (row.quantity > 0) {
        unknownQuantity += row.quantity;
      } else {
        const removed = -row.quantity;
        const unknownUsed = Math.min(unknownQuantity, removed);
        unknownQuantity -= unknownUsed;
        const knownUsed = Math.min(knownQuantity, removed - unknownUsed);
        const average = knownQuantity ? knownValue / knownQuantity : 0;
        knownQuantity -= knownUsed;
        knownValue = Math.max(0, knownValue - average * knownUsed);
      }
    }
  }
  return (productId, _date, saleId) => saleCosts.get(`${saleId}:${productId}`) ?? null;
}

function eventOrder(event) {
  if (event.type === "purchase") return 0;
  if (event.type === "movement" && event.quantity > 0) return 1;
  if (event.type === "sale") return 2;
  return 3;
}

export function summarizeProfit(sales, costFor) {
  const products = new Map();
  let profit = 0;
  let missingUnits = 0;
  let knownUnits = 0;
  for (const sale of sales) {
    for (const item of sale.items) {
      const product = products.get(item.id) || { name: item.name, quantity: 0, revenue: 0, profit: 0, missingUnits: 0, knownUnits: 0 };
      const cost = costFor(item.id, sale.date, sale.id);
      product.quantity += item.quantity;
      product.revenue += item.price * item.quantity;
      if (cost === null) {
        product.missingUnits += item.quantity;
        missingUnits += item.quantity;
      } else {
        const amount = (item.price - cost) * item.quantity;
        product.profit += amount;
        profit += amount;
        product.knownUnits += item.quantity;
        knownUnits += item.quantity;
      }
      products.set(item.id, product);
    }
  }
  return { profit, missingUnits, knownUnits, products: [...products.values()].sort((a, b) => b.quantity - a.quantity) };
}
