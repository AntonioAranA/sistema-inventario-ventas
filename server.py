import hashlib, hmac, json, mimetypes, os, secrets, sqlite3, uuid
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import wraps
from urllib.parse import unquote, urlparse
from backup_validation import validate_backup

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("INVENTORY_DB", ROOT / "data" / "inventory.db"))
PORT = int(os.environ.get("INVENTORY_PORT", "8000"))
SECURE_COOKIES = os.environ.get("INVENTORY_COOKIE_SECURE", "0") == "1"
PUBLIC_ORIGIN = os.environ.get("INVENTORY_PUBLIC_ORIGIN", "").rstrip("/")
TRUST_PROXY = os.environ.get("INVENTORY_TRUST_PROXY", "0") == "1"
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_IP_MAX_ATTEMPTS = 30
LOGIN_BLOCK_SECONDS = 15 * 60

if PUBLIC_ORIGIN:
    configured_origin=urlparse(PUBLIC_ORIGIN)
    if configured_origin.scheme!="https" or not configured_origin.netloc or configured_origin.path or configured_origin.query or configured_origin.fragment or not SECURE_COOKIES:
        raise RuntimeError("INVENTORY_PUBLIC_ORIGIN requiere un origen HTTPS valido e INVENTORY_COOKIE_SECURE=1")

class DatabaseConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def connect():
    db = sqlite3.connect(DB_PATH, factory=DatabaseConnection)
    if os.name == "posix":
        os.chmod(DB_PATH, 0o600)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def snapshot_database():
    """Save a consistent SQLite snapshot before replacing business data."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot_dir = DB_PATH.parent / "backups"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(snapshot_dir, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = snapshot_dir / f"inventory-before-restore-{stamp}-{uuid.uuid4().hex[:8]}.db"
    try:
        destination = sqlite3.connect(target)
        try:
            with connect() as source:
                source.backup(destination)
        finally:
            destination.close()
        if os.name == "posix":
            os.chmod(target, 0o600)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    cutoff = datetime.now(timezone.utc).timestamp() - 90 * 86400
    snapshots = sorted(snapshot_dir.glob("inventory-before-restore-*.db"), reverse=True)
    for index, snapshot in enumerate(snapshots):
        try:
            if snapshot.stat().st_mtime < cutoff or index >= 10:
                snapshot.unlink()
        except OSError:
            pass
    return target

def now(): return datetime.now(timezone.utc).isoformat()

def next_sequence(db, table, prefix):
    # Restored histories can have gaps or externally assigned folios.
    if table not in ("sales", "purchases"):
        raise ValueError("Tabla inválida")
    sequence = db.execute(f"SELECT COUNT(*)+1 FROM {table}").fetchone()[0]
    while db.execute(f"SELECT 1 FROM {table} WHERE folio=?", (f"{prefix}-{sequence:04d}",)).fetchone():
        sequence += 1
    return sequence

def hash_password(password,salt):
    return hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),210000).hex()

def verify_password(password,salt,expected):
    return hmac.compare_digest(hash_password(password,salt),expected)

def hash_session(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def user_json(row):
    return {"id":row["id"],"name":row["name"],"username":row["username"],"role":row["role"],"active":row["active"]}

def integer(value, label, minimum=0):
    if type(value) is not int or not minimum <= value <= 1_000_000_000:
        raise ValueError(f"{label}: ingresa un número entero entre {minimum} y 1000000000")
    return value

def line_items(data):
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 500 or any(not isinstance(item, dict) for item in items):
        raise ValueError("Agrega una lista válida de productos")
    return items

def api_errors(method):
    @wraps(method)
    def handle(self):
        try:
            return method(self)
        except (ValueError, TypeError, OverflowError):
            self.json({"error": "La solicitud contiene datos inválidos"}, 400)
        except sqlite3.IntegrityError:
            self.json({"error": "La operación entra en conflicto con los datos actuales"}, 409)
        except sqlite3.OperationalError:
            self.json({"error": "La base de datos no está disponible. Intenta nuevamente."}, 503)
    return handle

def initialize_database():
    DB_PATH.parent.mkdir(exist_ok=True)
    with connect() as db:
        first_creation = not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='products'").fetchone()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS products(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, sku TEXT NOT NULL UNIQUE COLLATE NOCASE,
          category TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0),
          stock INTEGER NOT NULL CHECK(stock>=0), min_stock INTEGER NOT NULL CHECK(min_stock>=0),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sales(
          id TEXT PRIMARY KEY, folio TEXT NOT NULL UNIQUE, customer TEXT NOT NULL DEFAULT '',
          total INTEGER NOT NULL CHECK(total>=0), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sale_items(
          id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id TEXT NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
          product_id TEXT NOT NULL, product_name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0),
          quantity INTEGER NOT NULL CHECK(quantity>0));
        CREATE TABLE IF NOT EXISTS inventory_movements(
          id TEXT PRIMARY KEY, product_id TEXT NOT NULL, product_name TEXT NOT NULL,
          movement_type TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity != 0),
          reason TEXT NOT NULL, responsible TEXT NOT NULL, sale_id TEXT,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS suppliers(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, tax_id TEXT NOT NULL DEFAULT '',
          phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS purchases(
          id TEXT PRIMARY KEY, folio TEXT NOT NULL UNIQUE, supplier_id TEXT NOT NULL REFERENCES suppliers(id),
          supplier_name TEXT NOT NULL, document TEXT NOT NULL DEFAULT '', responsible TEXT NOT NULL,
          notes TEXT NOT NULL DEFAULT '', total INTEGER NOT NULL CHECK(total>=0), created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS purchase_items(
          id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_id TEXT NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
          product_id TEXT NOT NULL, product_name TEXT NOT NULL, unit_cost INTEGER NOT NULL CHECK(unit_cost>=0),
          quantity INTEGER NOT NULL CHECK(quantity>0));
        CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY, name TEXT NOT NULL, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          password_hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(
          client_key TEXT PRIMARY KEY, window_started REAL NOT NULL,
          failures INTEGER NOT NULL, blocked_until REAL NOT NULL DEFAULT 0);
        """)
        # Old releases stored bearer tokens directly; invalidate them on upgrade.
        db.execute("DELETE FROM sessions WHERE length(token) != 64")
        if first_creation:
            created = now()
            examples = [
              ("Café molido 500 g","CAF-001","Abarrotes",6990,18,5),
              ("Té negro 20 bolsas","TE-020","Abarrotes",3290,4,6),
              ("Galletas de avena","GAL-014","Snacks",2490,3,5),
              ("Agua mineral 1.5 L","AGU-015","Bebidas",1290,26,8),
              ("Chocolate 70% cacao","CHO-070","Snacks",3990,12,4),
              ("Leche entera 1 L","LEC-001","Lácteos",1390,2,6)]
            db.executemany("INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?)",
              [(str(uuid.uuid4()),*item,created,created) for item in examples])
        baseline_time = now()
        products_without_history = db.execute("""SELECT * FROM products p WHERE p.stock != 0 AND NOT EXISTS(
          SELECT 1 FROM inventory_movements m WHERE m.product_id = p.id)""").fetchall()
        db.executemany("INSERT INTO inventory_movements VALUES(?,?,?,?,?,?,?,?,?)", [
          (str(uuid.uuid4()), product["id"], product["name"], "initial", product["stock"],
           "Stock inicial", "Sistema", None, baseline_time)
          for product in products_without_history
        ])

def product_json(row):
    return {"id":row["id"],"name":row["name"],"sku":row["sku"],"category":row["category"],
            "price":row["price"],"stock":row["stock"],"min":row["min_stock"]}

def get_state():
    with connect() as db:
        db.execute("BEGIN")
        products = [product_json(row) for row in db.execute("SELECT * FROM products ORDER BY name")]
        sales = []
        for sale in db.execute("SELECT * FROM sales ORDER BY created_at DESC"):
            items = [dict(row) for row in db.execute(
              "SELECT product_id id,product_name name,price,quantity FROM sale_items WHERE sale_id=?",(sale["id"],))]
            sales.append({"id":sale["id"],"folio":sale["folio"],"date":sale["created_at"],
                          "customer":sale["customer"],"total":sale["total"],"items":items})
        movements = [dict(row) for row in db.execute(
          """SELECT id,product_id AS productId,product_name AS productName,
          movement_type AS type,quantity,reason,responsible,sale_id AS saleId,created_at AS date
          FROM inventory_movements ORDER BY created_at DESC""")]
        suppliers = [dict(row) for row in db.execute(
          "SELECT id,name,tax_id AS taxId,phone,email,created_at AS createdAt FROM suppliers ORDER BY name")]
        purchases=[]
        for purchase in db.execute("SELECT * FROM purchases ORDER BY created_at DESC"):
            items=[dict(row) for row in db.execute(
              "SELECT product_id AS productId,product_name AS productName,unit_cost AS unitCost,quantity FROM purchase_items WHERE purchase_id=?",(purchase["id"],))]
            purchases.append({"id":purchase["id"],"folio":purchase["folio"],"supplierId":purchase["supplier_id"],
              "supplierName":purchase["supplier_name"],"document":purchase["document"],"responsible":purchase["responsible"],
              "notes":purchase["notes"],"total":purchase["total"],"date":purchase["created_at"],"items":items})
        return {"products":products,"sales":sales,"movements":movements,"suppliers":suppliers,"purchases":purchases}

def validate_product(data):
    values = {key:str(data.get(key,"")).strip() for key in ("name","sku","category")}
    if not all(values.values()): raise ValueError("Completa los datos obligatorios del producto")
    price = integer(data.get("price"), "Precio")
    minimum = integer(data.get("min"), "Stock mínimo")
    if min(price,minimum)<0: raise ValueError("Precio y cantidades no pueden ser negativos")
    return {"id":str(data.get("id") or uuid.uuid4()),**values,"price":price,"min":minimum}

class Handler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if SECURE_COOKIES:
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    @api_errors
    def do_GET(self):
        if self.path == "/api/backup":
            if not self.require_role("admin"): return
            return self.json({"format": "almacen-backup", "version": 1, "exportedAt": now(), **get_state()})
        if self.path == "/api/auth/status":
            user=self.current_user(); return self.json({"authenticated":bool(user),"needsSetup":self.user_count()==0,"user":user})
        if self.path == "/api/users":
            if not self.require_role("admin"): return
            with connect() as db:
                users=[dict(row) for row in db.execute("SELECT id,name,username,role,active,created_at AS createdAt FROM users ORDER BY name")]
            return self.json(users)
        if self.path == "/api/state":
            if not self.require_user(): return
            state = get_state()
            if self.current_user()["role"] == "seller":
                for key in ("purchases", "suppliers", "movements"):
                    state[key] = []
            return self.json(state)
        self.static_file()

    @api_errors
    def do_POST(self):
        if not self.check_origin(): return
        if self.path == "/api/auth/setup": return self.setup_admin()
        if self.path == "/api/auth/login": return self.login()
        if self.path == "/api/auth/logout": return self.logout()
        if self.path == "/api/auth/password":
            if not self.require_user(): return
            return self.change_password()
        if self.path == "/api/users":
            if not self.require_role("admin"): return
            return self.save_user()
        if self.path == "/api/backup/restore":
            if not self.require_role("admin"): return
            return self.restore_backup()
        if not self.require_user(): return
        if self.path == "/api/products" and self.has_role("admin","inventory"): return self.save_product()
        permissions={"/api/sales":("admin","seller"),"/api/movements":("admin","inventory"),
          "/api/suppliers":("admin","inventory"),"/api/purchases":("admin","inventory")}
        if self.path in permissions and not self.has_role(*permissions[self.path]):
            return self.json({"error":"No tienes permiso para realizar esta acción"},403)
        if self.path == "/api/sales": return self.save_sale()
        if self.path == "/api/movements": return self.save_movement()
        if self.path == "/api/suppliers": return self.save_supplier()
        if self.path == "/api/purchases": return self.save_purchase()
        if self.path == "/api/products": return self.json({"error":"No tienes permiso para modificar productos"},403)
        self.send_error(404)

    @api_errors
    def do_DELETE(self):
        if not self.check_origin(): return
        if self.path.startswith("/api/users/"):
            if not self.require_role("admin"): return
            return self.delete_user(unquote(self.path.split("/api/users/", 1)[1]))
        if not self.require_role("admin","inventory"): return
        if self.path.startswith("/api/suppliers/"):
            supplier_id=unquote(self.path.split("/api/suppliers/",1)[1])
            try:
                with connect() as db: result=db.execute("DELETE FROM suppliers WHERE id=?",(supplier_id,))
                return self.json({"deleted":result.rowcount>0})
            except sqlite3.IntegrityError:
                return self.json({"error":"No se puede eliminar un proveedor con compras registradas"},409)
        if not self.path.startswith("/api/products/"): return self.send_error(404)
        product_id = unquote(self.path.split("/api/products/",1)[1])
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            product=db.execute("SELECT stock FROM products WHERE id=?",(product_id,)).fetchone()
            if product and product["stock"]>0: return self.json({"error":"No puedes eliminar un producto que todavía tiene stock"},409)
            result=db.execute("DELETE FROM products WHERE id=?",(product_id,))
        self.json({"deleted":result.rowcount>0})

    def save_product(self):
        try:
            product=validate_product(self.body()); timestamp=now()
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                previous=db.execute("SELECT * FROM products WHERE id=?",(product["id"],)).fetchone()
                product["stock"]=previous["stock"] if previous else 0
                db.execute("""INSERT INTO products VALUES(:id,:name,:sku,:category,:price,:stock,:min,:created,:updated)
                ON CONFLICT(id) DO UPDATE SET name=:name,sku=:sku,category=:category,price=:price,
                min_stock=:min,updated_at=:updated""",{**product,"created":timestamp,"updated":timestamp})
            self.json(product)
        except sqlite3.IntegrityError: self.json({"error":"Ese SKU ya está en uso"},409)
        except ValueError as error: self.json({"error":str(error)},400)

    def save_sale(self):
        try:
            data=self.body(); requested=line_items(data)
            if not requested: raise ValueError("La venta no contiene productos")
            with connect() as db:
                db.execute("BEGIN IMMEDIATE"); items=[]; seen=set()
                for entry in requested:
                    product_id = entry.get("id")
                    if not isinstance(product_id, str) or product_id in seen:
                        raise ValueError("Cada producto debe aparecer una sola vez en la venta")
                    seen.add(product_id)
                    product=db.execute("SELECT * FROM products WHERE id=?",(entry.get("id"),)).fetchone()
                    quantity=integer(entry.get("quantity"), "Cantidad", 1)
                    if not product or quantity<1 or product["stock"]<quantity:
                        raise ValueError(f"Stock insuficiente para {entry.get('name','el producto')}")
                    items.append({"id":product["id"],"name":product["name"],"price":product["price"],"quantity":quantity})
                sequence=next_sequence(db, "sales", "V")
                sale={"id":str(uuid.uuid4()),"folio":f"V-{sequence:04d}","date":now(),
                      "customer":str(data.get("customer","")).strip(),"items":items}
                sale["total"]=sum(i["price"]*i["quantity"] for i in items)
                db.execute("INSERT INTO sales VALUES(?,?,?,?,?)",(sale["id"],sale["folio"],sale["customer"],sale["total"],sale["date"]))
                for item in items:
                    db.execute("INSERT INTO sale_items(sale_id,product_id,product_name,price,quantity) VALUES(?,?,?,?,?)",
                      (sale["id"],item["id"],item["name"],item["price"],item["quantity"]))
                    db.execute("UPDATE products SET stock=stock-?,updated_at=? WHERE id=?",(item["quantity"],sale["date"],item["id"]))
                    self.insert_movement(db,item["id"],item["name"],"sale",-item["quantity"],
                      f"Venta {sale['folio']}",self.current_user()["name"],sale["id"],sale["date"])
            self.json(sale,201)
        except (ValueError,TypeError) as error: self.json({"error":str(error)},400)

    def save_movement(self):
        try:
            data=self.body(); product_id=str(data.get("productId", "")); kind=str(data.get("type", ""))
            allowed={"entry":1,"return":1,"loss":-1,"adjustment_in":1,"adjustment_out":-1}
            if kind not in allowed: raise ValueError("Tipo de movimiento inválido")
            quantity=integer(data.get("quantity"), "Cantidad", 1)*allowed[kind]
            reason=str(data.get("reason","")).strip(); responsible=self.current_user()["name"]
            if quantity==0 or not reason: raise ValueError("Completa todos los datos del movimiento")
            timestamp=now()
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                product=db.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
                if not product: raise ValueError("El producto ya no existe")
                if product["stock"]+quantity<0: raise ValueError("El movimiento dejaría el stock en negativo")
                db.execute("UPDATE products SET stock=stock+?,updated_at=? WHERE id=?",(quantity,timestamp,product_id))
                movement=self.insert_movement(db,product_id,product["name"],kind,quantity,reason,responsible,None,timestamp)
            self.json(movement,201)
        except (ValueError,TypeError) as error: self.json({"error":str(error)},400)

    def save_supplier(self):
        try:
            data=self.body(); name=str(data.get("name","")).strip()
            if not name: raise ValueError("Ingresa el nombre del proveedor")
            supplier={"id":str(data.get("id") or uuid.uuid4()),"name":name,
              "taxId":str(data.get("taxId","")).strip(),"phone":str(data.get("phone","")).strip(),
              "email":str(data.get("email","")).strip(),"createdAt":now()}
            with connect() as db:
                db.execute("""INSERT INTO suppliers VALUES(:id,:name,:taxId,:phone,:email,:createdAt)
                ON CONFLICT(id) DO UPDATE SET name=:name,tax_id=:taxId,phone=:phone,email=:email""",supplier)
            self.json(supplier)
        except ValueError as error: self.json({"error":str(error)},400)

    def save_purchase(self):
        try:
            data=self.body(); requested=line_items(data); supplier_id=str(data.get("supplierId", ""))
            responsible=self.current_user()["name"]
            if not requested: raise ValueError("Agrega productos a la compra")
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                supplier=db.execute("SELECT * FROM suppliers WHERE id=?",(supplier_id,)).fetchone()
                if not supplier: raise ValueError("Selecciona un proveedor válido")
                items=[]
                for entry in requested:
                    product=db.execute("SELECT * FROM products WHERE id=?",(entry.get("productId"),)).fetchone()
                    quantity=integer(entry.get("quantity"), "Cantidad", 1)
                    cost=integer(entry.get("unitCost"), "Costo unitario")
                    if not product or quantity<1 or cost<0: raise ValueError("Revisa los productos de la compra")
                    items.append({"productId":product["id"],"productName":product["name"],"quantity":quantity,"unitCost":cost})
                sequence=next_sequence(db, "purchases", "C"); timestamp=now()
                purchase={"id":str(uuid.uuid4()),"folio":f"C-{sequence:04d}","supplierId":supplier["id"],
                  "supplierName":supplier["name"],"document":str(data.get("document","")).strip(),
                  "responsible":responsible,"notes":str(data.get("notes","")).strip(),"items":items,"date":timestamp}
                purchase["total"]=sum(i["unitCost"]*i["quantity"] for i in items)
                db.execute("INSERT INTO purchases VALUES(?,?,?,?,?,?,?,?,?)",(purchase["id"],purchase["folio"],purchase["supplierId"],
                  purchase["supplierName"],purchase["document"],purchase["responsible"],purchase["notes"],purchase["total"],timestamp))
                for item in items:
                    db.execute("INSERT INTO purchase_items(purchase_id,product_id,product_name,unit_cost,quantity) VALUES(?,?,?,?,?)",
                      (purchase["id"],item["productId"],item["productName"],item["unitCost"],item["quantity"]))
                    db.execute("UPDATE products SET stock=stock+?,updated_at=? WHERE id=?",(item["quantity"],timestamp,item["productId"]))
                    reason=f"Compra {purchase['folio']}"+(f" · {purchase['document']}" if purchase["document"] else "")
                    self.insert_movement(db,item["productId"],item["productName"],"purchase",item["quantity"],reason,responsible,None,timestamp)
            self.json(purchase,201)
        except (ValueError,TypeError) as error: self.json({"error":str(error)},400)

    def insert_movement(self,db,product_id,product_name,kind,quantity,reason,responsible,sale_id,created):
        movement={"id":str(uuid.uuid4()),"productId":product_id,"productName":product_name,"type":kind,
                  "quantity":quantity,"reason":reason,"responsible":responsible,"saleId":sale_id,"date":created}
        db.execute("INSERT INTO inventory_movements VALUES(?,?,?,?,?,?,?,?,?)",
          (movement["id"],product_id,product_name,kind,quantity,reason,responsible,sale_id,created))
        return movement

    def setup_admin(self):
        retry=self.login_retry_after("__setup__")
        if retry: return self.rate_limited(retry)
        if self.user_count()>0: return self.json({"error":"La configuración inicial ya fue realizada"},409)
        try:
            data=self.body(); user=self.create_user(data,"admin",initial=True)
            self.clear_login_attempts("__setup__")
            self.start_session(user)
        except ValueError as error:
            retry=self.record_failed_login("__setup__")
            if retry: return self.rate_limited(retry)
            self.json({"error":str(error)},400)

    def login(self):
        data=self.body(); username=str(data.get("username","")).strip()
        password=str(data.get("password",""))
        identity=username.casefold() if len(username)<=128 else "__invalid__"
        retry=self.login_retry_after(identity)
        if retry: return self.rate_limited(retry)
        if len(username)>128 or len(password)>128:
            self.record_failed_login(identity)
            return self.json({"error":"Credenciales incorrectas"},401)
        with connect() as db: row=db.execute("SELECT * FROM users WHERE username=? AND active=1",(username,)).fetchone()
        valid=verify_password(password,row["salt"],row["password_hash"]) if row else verify_password(password,"00"*16,"00"*32)
        if not valid:
            retry=self.record_failed_login(identity)
            if retry: return self.rate_limited(retry)
            return self.json({"error":"Usuario o contraseña incorrectos"},401)
        self.clear_login_attempts(identity)
        self.start_session(user_json(row))

    def logout(self):
        token=self.session_token()
        if token:
            with connect() as db: db.execute("DELETE FROM sessions WHERE token=?",(hash_session(token),))
        self.send_response(204); self.send_header("Set-Cookie",self.session_cookie("",clear=True)); self.end_headers()

    def change_password(self):
        data=self.body(); current=self.current_user(); old=str(data.get("currentPassword","")); new=str(data.get("newPassword",""))
        if len(old)>128 or len(new)>128: return self.json({"error":"La contrasena es demasiado larga"},400)
        with connect() as db: row=db.execute("SELECT * FROM users WHERE id=?",(current["id"],)).fetchone()
        if not verify_password(old,row["salt"],row["password_hash"]): return self.json({"error":"La contraseña actual no es correcta"},400)
        if len(new)<8: return self.json({"error":"La nueva contraseña debe tener al menos 8 caracteres"},400)
        salt=secrets.token_hex(16); digest=hash_password(new,salt); token=self.session_token()
        with connect() as db:
            db.execute("UPDATE users SET password_hash=?,salt=? WHERE id=?",(digest,salt,current["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=? AND token!=?",(current["id"],hash_session(token)))
        self.json({"updated":True})

    def save_user(self):
        try:
            data=self.body(); user_id=str(data.get("id", ""))
            if user_id:
                role=str(data.get("role",""))
                if role not in ("admin","seller","inventory"): raise ValueError("Rol inválido")
                current=self.current_user()
                with connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    target=db.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
                    if not target: raise ValueError("El usuario no existe")
                    name=str(data.get("name",target["name"])).strip()
                    username=str(data.get("username",target["username"])).strip()
                    active_value=data.get("active",target["active"])
                    if type(active_value) is not bool and active_value not in (0,1):
                        raise ValueError("Estado de usuario inválido")
                    active=1 if active_value else 0
                    password=str(data.get("password",""))
                    if not name: raise ValueError("Ingresa un nombre")
                    if len(username)<3: raise ValueError("El nombre de usuario debe tener al menos 3 caracteres")
                    if len(username)>128: raise ValueError("El nombre de usuario no puede superar 128 caracteres")
                    if len(password)>128: raise ValueError("La contrasena es demasiado larga")
                    if password and len(password)<8: raise ValueError("La contraseña debe tener al menos 8 caracteres")
                    if current["id"]==user_id and not active: raise ValueError("No puedes desactivar tu propia cuenta")
                    if current["id"]==user_id and role!="admin": raise ValueError("No puedes cambiar tu propio rol de administrador")
                    if current["id"]==user_id and password:
                        raise ValueError("Para cambiar tu contraseña, usa la opción Mi cuenta")
                    if target["role"]=="admin" and target["active"] and (role!="admin" or not active):
                        active_admins=db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                        if active_admins<=1: raise ValueError("Debe permanecer al menos un administrador activo")
                    if password:
                        salt=secrets.token_hex(16)
                        digest=hash_password(password,salt)
                        db.execute("UPDATE users SET name=?,username=?,role=?,active=?,salt=?,password_hash=? WHERE id=?",
                          (name,username,role,active,salt,digest,user_id))
                        db.execute("DELETE FROM sessions WHERE user_id=?",(user_id,))
                    else:
                        db.execute("UPDATE users SET name=?,username=?,role=?,active=? WHERE id=?",
                          (name,username,role,active,user_id))
                    if not active or target["role"] != role or username.casefold()!=target["username"].casefold():
                        if current["id"]==user_id:
                            db.execute("DELETE FROM sessions WHERE user_id=? AND token!=?",(user_id,hash_session(self.session_token())))
                        else:
                            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
                    updated=db.execute("SELECT id,name,username,role,active FROM users WHERE id=?",(user_id,)).fetchone()
                return self.json(dict(updated))
            user=self.create_user(data,str(data.get("role",""))); self.json(user,201)
        except sqlite3.IntegrityError: self.json({"error":"Ese nombre de usuario ya existe"},409)
        except ValueError as error: self.json({"error":str(error)},400)

    def delete_user(self,user_id):
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            target=db.execute("SELECT role,active FROM users WHERE id=?",(user_id,)).fetchone()
            if not target: return self.json({"error":"El usuario no existe"},404)
            if self.current_user()["id"]==user_id:
                return self.json({"error":"No puedes eliminar tu propia cuenta"},400)
            if target["role"]=="admin" and target["active"]:
                active_admins=db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                if active_admins<=1:
                    return self.json({"error":"Debe permanecer al menos un administrador activo"},400)
            db.execute("DELETE FROM users WHERE id=?",(user_id,))
        return self.json({"deleted":True})

    def restore_backup(self):
        try:
            data = validate_backup(self.body())
            products, suppliers = data["products"], data["suppliers"]
            sales, movements, purchases = data["sales"], data["movements"], data["purchases"]
            snapshot_database()
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                for table in ("sale_items", "sales", "purchase_items", "purchases", "inventory_movements", "products", "suppliers"):
                    db.execute(f"DELETE FROM {table}")
                for item in suppliers:
                    db.execute("INSERT INTO suppliers(id,name,tax_id,phone,email,created_at) VALUES(?,?,?,?,?,?)", (str(item["id"]), str(item.get("name", "")).strip(), str(item.get("taxId", "")), str(item.get("phone", "")), str(item.get("email", "")), str(item.get("createdAt") or now())))
                for item in products:
                    db.execute("INSERT INTO products(id,name,sku,category,price,stock,min_stock,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (str(item["id"]), str(item["name"]).strip(), str(item["sku"]).strip(), str(item.get("category", "")).strip(), item["price"], item["stock"], item["min"], str(item.get("createdAt") or now()), str(item.get("updatedAt") or now())))
                for sale in sales:
                    db.execute("INSERT INTO sales(id,folio,customer,total,created_at) VALUES(?,?,?,?,?)", (str(sale["id"]), str(sale["folio"]), str(sale.get("customer", "")), sale["total"], str(sale.get("date") or now())))
                    for item in line_items({"items": sale.get("items", [])}):
                        db.execute("INSERT INTO sale_items(sale_id,product_id,product_name,price,quantity) VALUES(?,?,?,?,?)", (str(sale["id"]), str(item["id"]), str(item["name"]), item["price"], item["quantity"]))
                for movement in movements:
                    db.execute("INSERT INTO inventory_movements(id,product_id,product_name,movement_type,quantity,reason,responsible,sale_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (str(movement["id"]), str(movement["productId"]), str(movement["productName"]), str(movement["type"]), int(movement["quantity"]), str(movement.get("reason", "")), str(movement.get("responsible", "")), movement.get("saleId"), str(movement.get("date") or now())))
                for purchase in purchases:
                    db.execute("INSERT INTO purchases(id,folio,supplier_id,supplier_name,document,responsible,notes,total,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (str(purchase["id"]), str(purchase["folio"]), str(purchase["supplierId"]), str(purchase["supplierName"]), str(purchase.get("document", "")), str(purchase.get("responsible", "")), str(purchase.get("notes", "")), purchase["total"], str(purchase.get("date") or now())))
                    for item in line_items({"items": purchase.get("items", [])}):
                        db.execute("INSERT INTO purchase_items(purchase_id,product_id,product_name,unit_cost,quantity) VALUES(?,?,?,?,?)", (str(purchase["id"]), str(item["productId"]), str(item["productName"]), item["unitCost"], item["quantity"]))
            self.json({"restored": True})
        except (KeyError, TypeError, ValueError) as error:
            self.json({"error": f"Respaldo inválido: {error}"}, 400)
        except sqlite3.IntegrityError:
            self.json({"error": "El respaldo contiene datos incompatibles. No se modificó la información actual."}, 400)

    def create_user(self,data,role,initial=False):
        name=str(data.get("name","")).strip(); username=str(data.get("username","")).strip(); password=str(data.get("password",""))
        if len(username)>128 or len(password)>128: raise ValueError("El usuario o la contrasena es demasiado largo")
        if role not in ("admin","seller","inventory"): raise ValueError("Rol inválido")
        if not name or len(username)<3 or len(password)<8: raise ValueError("Completa los datos y usa una contraseña de al menos 8 caracteres")
        salt=secrets.token_hex(16); digest=hash_password(password,salt); created=now(); user_id=str(uuid.uuid4())
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if initial and db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                raise ValueError("La configuración inicial ya fue realizada")
            db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,1,?)",(user_id,name,username,digest,salt,role,created))
        return {"id":user_id,"name":name,"username":username,"role":role,"active":1,"createdAt":created}

    def start_session(self,user):
        token=secrets.token_urlsafe(32); expires=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<=?",(now(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)",(hash_session(token),user["id"],expires))
        content=json.dumps({"user":user},ensure_ascii=False).encode()
        self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Set-Cookie",self.session_cookie(token))
        self.send_header("Content-Length",str(len(content))); self.end_headers(); self.wfile.write(content)

    def session_token(self):
        for part in self.headers.get("Cookie","").split(";"):
            key,_,value=part.strip().partition("=")
            if key==self.session_cookie_name(): return value
        return None

    @staticmethod
    def session_cookie_name():
        return "__Host-session" if SECURE_COOKIES else "session"

    def session_cookie(self,token,clear=False):
        name=self.session_cookie_name()
        secure="; Secure" if SECURE_COOKIES else ""
        age="0" if clear else "604800"
        return f"{name}={token}; Path=/; HttpOnly; SameSite=Strict{secure}; Max-Age={age}"

    def check_origin(self):
        origin=self.headers.get("Origin")
        if not origin:
            if SECURE_COOKIES:
                self.json({"error":"Falta el origen de la solicitud"},403)
                return False
            return True
        expected=PUBLIC_ORIGIN or f"{'https' if SECURE_COOKIES else 'http'}://{self.headers.get('Host','')}"
        if origin.rstrip("/")==expected:
            return True
        self.json({"error":"Origen de solicitud no permitido"},403)
        return False

    def client_key(self,identity,scope="account"):
        address=self.client_address[0] if self.client_address else "unknown"
        if TRUST_PROXY:
            forwarded=self.headers.get("X-Forwarded-For", "").split(",",1)[0].strip()
            if forwarded: address=forwarded
        return hashlib.sha256(f"{address}\0{scope}\0{identity}".encode("utf-8")).hexdigest()

    def login_retry_after(self,identity):
        keys=(self.client_key(identity),self.client_key("",scope="ip"))
        with connect() as db:
            rows=[db.execute("SELECT blocked_until FROM login_attempts WHERE client_key=?",(key,)).fetchone() for key in keys]
        now_value=time.time()
        return max((max(1,int(row["blocked_until"]-now_value+0.999)) for row in rows if row and row["blocked_until"]>now_value),default=0)

    def record_failed_login(self,identity):
        timestamp=time.time(); retry_after=0
        buckets=((self.client_key(identity),LOGIN_MAX_ATTEMPTS),(self.client_key("",scope="ip"),LOGIN_IP_MAX_ATTEMPTS))
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE window_started<? AND blocked_until<?",
              (timestamp-LOGIN_WINDOW_SECONDS,timestamp))
            for key,limit in buckets:
                row=db.execute("SELECT * FROM login_attempts WHERE client_key=?",(key,)).fetchone()
                if row and row["blocked_until"]>timestamp:
                    retry_after=max(retry_after,int(row["blocked_until"]-timestamp+0.999))
                    continue
                if not row or timestamp-row["window_started"]>=LOGIN_WINDOW_SECONDS:
                    failures=1; started=timestamp
                else:
                    failures=row["failures"]+1; started=row["window_started"]
                blocked=timestamp+LOGIN_BLOCK_SECONDS if failures>=limit else 0
                db.execute("INSERT INTO login_attempts VALUES(?,?,?,?) ON CONFLICT(client_key) DO UPDATE SET window_started=excluded.window_started,failures=excluded.failures,blocked_until=excluded.blocked_until",
                  (key,started,failures,blocked))
                retry_after=max(retry_after,LOGIN_BLOCK_SECONDS if blocked else 0)
        return retry_after

    def clear_login_attempts(self,identity):
        with connect() as db:
            db.execute("DELETE FROM login_attempts WHERE client_key=?",(self.client_key(identity),))

    def rate_limited(self,retry):
        content=json.dumps({"error":"Demasiados intentos. Espera antes de volver a ingresar."},ensure_ascii=False).encode()
        self.send_response(429); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Retry-After",str(retry)); self.send_header("Content-Length",str(len(content)))
        self.end_headers(); self.wfile.write(content)

    def current_user(self):
        token=self.session_token()
        if not token: return None
        with connect() as db:
            row=db.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
              WHERE s.token=? AND s.expires_at>? AND u.active=1""",(hash_session(token),now())).fetchone()
        return user_json(row) if row else None

    def user_count(self):
        with connect() as db: return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def has_role(self,*roles):
        user=self.current_user(); return bool(user and user["role"] in roles)

    def require_user(self):
        if self.current_user(): return True
        self.json({"error":"Debes iniciar sesión"},401); return False

    def require_role(self,*roles):
        if not self.require_user(): return False
        if self.has_role(*roles): return True
        self.json({"error":"No tienes permiso para realizar esta acción"},403); return False

    def body(self):
        length=int(self.headers.get("Content-Length",0))
        limit = 20_000_000 if self.path == "/api/backup/restore" else 1_000_000
        if length<1 or length>limit: raise ValueError("Tamaño de solicitud inválido")
        try:
            data=json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data,dict): raise ValueError("Se esperaba un objeto JSON")
            return data
        except (json.JSONDecodeError,UnicodeDecodeError):
            raise ValueError("JSON inválido")

    def json(self,data,status=200):
        content=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(content))); self.end_headers(); self.wfile.write(content)

    def static_file(self):
        path=urlparse(self.path).path; relative="index.html" if path=="/" else unquote(path.lstrip("/"))
        target=(ROOT/relative).resolve()
        public_root = ROOT / "src"
        allowed = target in (ROOT / "index.html", ROOT / "styles.css") or (
            public_root in target.parents and target.suffix in (".js", ".css", ".html")
        )
        if not allowed: return self.send_error(404)
        if (ROOT not in target.parents and target!=ROOT) or not target.is_file(): return self.send_error(404)
        content=target.read_bytes(); mime=mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",mime+("; charset=utf-8" if mime.startswith("text/") or "javascript" in mime else ""))
        self.send_header("Content-Length",str(len(content))); self.end_headers(); self.wfile.write(content)

if __name__ == "__main__":
    initialize_database()
    print(f"Mi Almacén disponible en http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()
