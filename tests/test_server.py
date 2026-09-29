"""Regresiones de la API. Cada prueba usa SQLite y un puerto temporales."""
import http.cookiejar
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from http.server import ThreadingHTTPServer

import server


class QuietHandler(server.Handler):
    def log_message(self, *_):
        pass


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_db = server.DB_PATH
        server.DB_PATH = Path(self.folder.name) / "inventory.db"
        server.initialize_database()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"
        self.client = self.new_client()
        status, self.admin = self.call("/api/auth/setup", {
            "name": "Administrador", "username": "admin", "password": "test-password-123",
        })
        self.assertEqual(status, 200)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()
        server.DB_PATH = self.old_db
        self.folder.cleanup()

    @staticmethod
    def new_client():
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, data=None, method=None, client=None, raw=None):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + path, body, {"Content-Type": "application/json"}, method=method)
        try:
            response = (client or self.client).open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            content = response.read()
            result = json.loads(content) if content and "application/json" in response.headers.get("Content-Type", "") else content
            return response.status, result

    def product(self):
        _, data = self.call("/api/products", {
            "name": "Producto", "sku": "TEST", "category": "Prueba", "price": 120, "min": 1, "stock": 999,
        })
        self.assertEqual(data["stock"], 0)
        return data

    def entry(self, product, quantity=5):
        return self.call("/api/movements", {
            "productId": product["id"], "type": "entry", "quantity": quantity, "reason": "Recepción",
        })

    def test_private_files_are_not_served_even_without_login(self):
        anonymous = self.new_client()
        for path in ("/server.py", "/data/inventory.db", "/.gitignore", "/src/../server.py", "/%2e%2e/server.py"):
            with self.subTest(path=path):
                self.assertEqual(self.call(path, client=anonymous)[0], 404)
        for path in ("/", "/styles.css", "/src/js/app.js", "/src/css/theme.css"):
            self.assertEqual(self.call(path, client=anonymous)[0], 200)

    def test_bad_json_and_invalid_item_shapes_return_json_errors(self):
        for raw in (b"{broken", b"[]", b"null", b'"hello"'):
            status, result = self.call("/api/auth/login", raw=raw)
            self.assertEqual(status, 400)
            self.assertIn("error", result)
        for items in (None, "oops", [None], [1], {}):
            self.assertEqual(self.call("/api/sales", {"items": items})[0], 400)

    def test_negative_fractional_and_boolean_quantities_do_not_change_stock(self):
        product = self.product()
        for quantity in (-2, 0, 1.5, True, "2", 10**30):
            for kind in ("entry", "loss"):
                with self.subTest(quantity=quantity, kind=kind):
                    self.assertEqual(self.call("/api/movements", {
                        "productId": product["id"], "type": kind, "quantity": quantity, "reason": "Prueba",
                    })[0], 400)
        saved = next(p for p in server.get_state()["products"] if p["id"] == product["id"])
        self.assertEqual(saved["stock"], 0)

    def test_catalog_edit_preserves_stock_and_rejects_fractional_prices(self):
        product = self.product()
        self.entry(product)
        status, edited = self.call("/api/products", {**product, "name": "Nuevo nombre", "stock": 999})
        self.assertEqual(status, 200)
        self.assertEqual(edited["stock"], 5)
        self.assertEqual(self.call("/api/products", {**product, "price": 10.9})[0], 400)
        self.assertEqual(self.call(f'/api/products/{product["id"]}', method="DELETE")[0], 409)

    def test_duplicate_sale_lines_and_invalid_purchase_roll_back(self):
        product = self.product()
        self.entry(product)
        line = {"id": product["id"], "quantity": 4}
        self.assertEqual(self.call("/api/sales", {"items": [line, line]})[0], 400)
        _, supplier = self.call("/api/suppliers", {"name": "Proveedor"})
        self.assertEqual(self.call("/api/purchases", {"supplierId": supplier["id"], "items": [
            {"productId": product["id"], "quantity": 3, "unitCost": 10},
            {"productId": "missing", "quantity": 1, "unitCost": 10},
        ]})[0], 400)
        state = server.get_state()
        self.assertEqual(next(p["stock"] for p in state["products"] if p["id"] == product["id"]), 5)
        self.assertEqual(state["sales"], [])
        self.assertEqual(state["purchases"], [])

    def test_concurrent_sales_do_not_oversell(self):
        product = self.product()
        self.entry(product, 1)
        def sell(_):
            return self.call("/api/sales", {"items": [{"id": product["id"], "quantity": 1}]})[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(sell, range(2))), [201, 400])
        self.assertEqual(len(server.get_state()["sales"]), 1)

    def test_purchase_sale_and_movement_responsibility(self):
        product = self.product()
        _, supplier = self.call("/api/suppliers", {"name": "Proveedor"})
        status, purchase = self.call("/api/purchases", {
            "supplierId": supplier["id"], "responsible": "Falso", "items": [
                {"productId": product["id"], "quantity": 2, "unitCost": 70},
            ],
        })
        self.assertEqual(status, 201)
        self.assertEqual(purchase["total"], 140)
        self.assertEqual(purchase["responsible"], "Administrador")
        status, sale = self.call("/api/sales", {"items": [{"id": product["id"], "quantity": 1, "price": 1}]})
        self.assertEqual(status, 201)
        self.assertEqual(sale["total"], 120)
        state = server.get_state()
        movements = [m for m in state["movements"] if m["productId"] == product["id"]]
        self.assertEqual(sum(m["quantity"] for m in movements), 1)
        self.assertTrue(all(m["responsible"] == "Administrador" for m in movements))

    def test_password_change_revokes_other_session(self):
        second = self.new_client()
        self.call("/api/auth/login", {"username": "admin", "password": "test-password-123"}, client=second)
        self.assertEqual(self.call("/api/auth/password", {
            "currentPassword": "incorrecta", "newPassword": "new-password-456",
        })[0], 400)
        self.assertEqual(self.call("/api/auth/password", {
            "currentPassword": "test-password-123", "newPassword": "new-password-456",
        })[0], 200)
        self.assertEqual(self.call("/api/state", client=second)[0], 401)
        self.assertEqual(self.call("/api/state")[0], 200)

    def test_disabled_user_does_not_recover_old_session_when_reenabled(self):
        _, user = self.call("/api/users", {"name": "Vendedor", "username": "seller", "password": "seller-password", "role": "seller"})
        client = self.new_client()
        self.call("/api/auth/login", {"username": "seller", "password": "seller-password"}, client=client)
        self.assertEqual(self.call("/api/users", {**user, "active": False})[0], 200)
        self.assertEqual(self.call("/api/users", {**user, "active": True})[0], 200)
        self.assertEqual(self.call("/api/state", client=client)[0], 401)

    def test_roles_and_self_protection(self):
        self.call("/api/suppliers", {"name": "Contacto privado"})
        _, user = self.call("/api/users", {"name": "Vendedor", "username": "seller", "password": "seller-password", "role": "seller"})
        client = self.new_client()
        self.call("/api/auth/login", {"username": "seller", "password": "seller-password"}, client=client)
        self.assertEqual(self.call("/api/products", {}, client=client)[0], 403)
        self.assertEqual(self.call("/api/users", client=client)[0], 403)
        _, state = self.call("/api/state", client=client)
        self.assertEqual(state["suppliers"], [])
        self.assertEqual(state["movements"], [])
        admin = self.admin["user"]
        self.assertEqual(self.call("/api/users", {**admin, "active": False})[0], 400)
        self.assertEqual(self.call("/api/users", {**admin, "role": "seller"})[0], 400)
        self.assertEqual(self.call("/api/auth/setup", {"name": "Otro", "username": "other", "password": "other-password"})[0], 409)

    def test_restart_does_not_recreate_deleted_catalog(self):
        with server.connect() as db:
            db.execute("DELETE FROM products")
        server.initialize_database()
        self.assertEqual(server.get_state()["products"], [])


if __name__ == "__main__":
    unittest.main()
