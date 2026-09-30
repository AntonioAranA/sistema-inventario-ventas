"""Validate business backups before any existing records are replaced."""
from datetime import datetime

COLLECTIONS = ("products", "suppliers", "sales", "purchases", "movements")
MAX_INTEGER = 2**53 - 1


def text(row, field, required=True):
    value = row.get(field, "" if not required else None)
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"Campo inválido en el respaldo: {field}")
    return value


def number(row, field, minimum=0):
    value = row.get(field)
    if type(value) is not int or not minimum <= value <= MAX_INTEGER:
        raise ValueError(f"Número inválido en el respaldo: {field}")
    return value


def date(row, field):
    value = text(row, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
    except ValueError:
        raise ValueError(f"Fecha inválida en el respaldo: {field}") from None


def unique(rows, field, ignore_case=False):
    values = [text(row, field) for row in rows]
    if ignore_case:
        values = [value.casefold() for value in values]
    if len(values) != len(set(values)):
        raise ValueError(f"El respaldo contiene valores duplicados: {field}")


def validate_backup(data):
    if not isinstance(data, dict):
        raise ValueError("Selecciona un respaldo JSON del sistema")
    if "version" in data and (type(data["version"]) is not int or data["version"] != 1):
        raise ValueError("La versión del respaldo no es compatible")
    if "version" in data and data.get("format") != "almacen-backup":
        raise ValueError("El formato del respaldo no es compatible")
    date(data, "exportedAt")
    for key in COLLECTIONS:
        rows = data.get(key)
        if not isinstance(rows, list) or len(rows) > 100_000:
            raise ValueError(f"El respaldo está incompleto o es inválido: {key}")
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError(f"Registros inválidos en {key}")
        unique(rows, "id")

    unique(data["products"], "sku", ignore_case=True)
    for product in data["products"]:
        for field in ("name", "sku", "category"):
            text(product, field)
        for field in ("price", "stock", "min"):
            number(product, field)
        for field in ("createdAt", "updatedAt"):
            if field in product:
                date(product, field)
    for supplier in data["suppliers"]:
        text(supplier, "name")
        date(supplier, "createdAt")
        for field in ("taxId", "phone", "email"):
            text(supplier, field, required=False)

    supplier_ids = {row["id"] for row in data["suppliers"]}
    sale_ids = {row["id"] for row in data["sales"]}
    for collection in ("sales", "purchases"):
        unique(data[collection], "folio")
        for record in data[collection]:
            date(record, "date")
            if collection == "purchases":
                if text(record, "supplierId") not in supplier_ids:
                    raise ValueError("Una compra hace referencia a un proveedor inexistente")
                for field in ("supplierName", "responsible"):
                    text(record, field)
                for field in ("document", "notes"):
                    text(record, field, required=False)
            else:
                text(record, "customer", required=False)
            items = record.get("items")
            if not isinstance(items, list) or not 1 <= len(items) <= 500:
                raise ValueError("Una operación no tiene un detalle válido")
            total = 0
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Detalle de operación inválido")
                is_sale = collection == "sales"
                text(item, "id" if is_sale else "productId")
                text(item, "name" if is_sale else "productName")
                total += number(item, "price" if is_sale else "unitCost") * number(item, "quantity", 1)
            if number(record, "total") != total:
                raise ValueError("El total de una operación no coincide con sus productos")
            if collection == "sales":
                unique(items, "id")

    kinds = {"initial", "entry", "purchase", "sale", "return", "loss", "adjustment", "adjustment_in", "adjustment_out"}
    balances = {}
    for movement in data["movements"]:
        for field in ("productId", "productName", "reason", "responsible"):
            text(movement, field)
        date(movement, "date")
        quantity = number(movement, "quantity", -MAX_INTEGER)
        kind = text(movement, "type")
        if not quantity or kind not in kinds:
            raise ValueError("Movimiento inválido en el respaldo")
        if kind in {"sale", "loss", "adjustment_out"} and quantity > 0:
            raise ValueError("Una salida de inventario tiene cantidad positiva")
        if kind in {"initial", "entry", "purchase", "return", "adjustment_in"} and quantity < 0:
            raise ValueError("Una entrada de inventario tiene cantidad negativa")
        sale_id = movement.get("saleId")
        if sale_id is not None and (not isinstance(sale_id, str) or sale_id not in sale_ids):
            raise ValueError("Un movimiento hace referencia a una venta inexistente")
        balances[movement["productId"]] = balances.get(movement["productId"], 0) + quantity
    for product in data["products"]:
        if balances.get(product["id"], 0) != product["stock"]:
            raise ValueError("Las existencias no coinciden con el historial de movimientos")
    return data
