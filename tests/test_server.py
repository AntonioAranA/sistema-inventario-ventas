"""Regresiones de la API. Cada prueba usa SQLite y un puerto temporales."""
import http.cookiejar
import json
import sqlite3
import tempfile
import threading
import unittest
from copy import deepcopy
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

    def call(self, path, data=None, method=None, client=None, raw=None, origin=None):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(self.base + path, body, headers, method=method)
        try:
            response = (client or self.client).open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.response_headers = dict(response.headers)
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

    def test_login_attempts_are_throttled_per_client(self):
        for attempt in range(server.LOGIN_MAX_ATTEMPTS):
            status, _ = self.call("/api/auth/login", {"username": "admin", "password": "wrong-password"})
        self.assertEqual(status, 429)
        self.assertIn("Retry-After", self.response_headers)
        self.assertEqual(self.call("/api/auth/login", {
            "username": "admin", "password": "test-password-123",
        })[0], 429)

    def test_login_attempts_are_also_limited_across_usernames(self):
        old_limit = server.LOGIN_IP_MAX_ATTEMPTS
        try:
            server.LOGIN_IP_MAX_ATTEMPTS = 3
            for attempt in range(server.LOGIN_IP_MAX_ATTEMPTS):
                status, _ = self.call("/api/auth/login", {
                    "username": f"missing-{attempt}", "password": "wrong-password",
                })
            self.assertEqual(status, 429)
        finally:
            server.LOGIN_IP_MAX_ATTEMPTS = old_limit

    def test_security_headers_and_secure_cookie_configuration(self):
        status, _ = self.call("/api/auth/status", client=self.new_client())
        self.assertEqual(status, 200)
        self.assertEqual(self.response_headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", self.response_headers["Content-Security-Policy"])
        old_secure = server.SECURE_COOKIES
        try:
            server.SECURE_COOKIES = True
            self.assertEqual(self.call("/api/auth/login", {
                "username": "admin", "password": "test-password-123",
            }, client=self.new_client(), origin=self.base.replace("http://", "https://", 1))[0], 200)
            cookie = self.response_headers["Set-Cookie"]
            self.assertTrue(cookie.startswith("__Host-session="))
            self.assertIn("; Secure", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            self.assertIn("Strict-Transport-Security", self.response_headers)
            token = cookie.split("=", 1)[1].split(";", 1)[0]
            with server.connect() as db:
                stored = db.execute("SELECT 1 FROM sessions WHERE token=?", (server.hash_session(token),)).fetchone()
            self.assertIsNotNone(stored)
        finally:
            server.SECURE_COOKIES = old_secure

    def test_upgrade_removes_legacy_plaintext_session_tokens(self):
        user_id = self.admin["user"]["id"]
        with server.connect() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?)", ("legacy-bearer-token", user_id, server.now()))
        server.initialize_database()
        with server.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT 1 FROM sessions WHERE token=?", ("legacy-bearer-token",),
            ).fetchone())

    def test_cross_origin_mutations_are_rejected(self):
        request = urllib.request.Request(
            self.base + "/api/products",
            json.dumps({"name": "Injected", "sku": "BAD", "category": "Test", "price": 100, "min": 1}).encode(),
            {"Content-Type": "application/json", "Origin": "https://attacker.example"},
            method="POST",
        )
        try:
            response = self.client.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.status, 403)
        self.assertFalse(any(product["sku"] == "BAD" for product in server.get_state()["products"]))
        same_origin = urllib.request.Request(
            self.base + "/api/auth/login",
            json.dumps({"username": "admin", "password": "test-password-123"}).encode(),
            {"Content-Type": "application/json", "Origin": self.base},
            method="POST",
        )
        with self.new_client().open(same_origin, timeout=10) as response:
            self.assertEqual(response.status, 200)

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

    def test_admin_can_edit_and_delete_other_users(self):
        _, user = self.call("/api/users", {
            "name": "Vendedor", "username": "seller", "password": "seller-password", "role": "seller",
        })
        client = self.new_client()
        self.call("/api/auth/login", {"username": "seller", "password": "seller-password"}, client=client)
        status, updated = self.call("/api/users", {
            "id": user["id"], "name": "Encargado", "username": "staff", "role": "inventory",
            "active": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual((updated["name"], updated["username"], updated["role"]), ("Encargado", "staff", "inventory"))
        self.assertEqual(self.call("/api/state", client=client)[0], 401)
        self.assertEqual(self.call("/api/auth/login", {"username": "seller", "password": "seller-password"}, client=self.new_client())[0], 401)
        fresh = self.new_client()
        self.assertEqual(self.call("/api/auth/login", {"username": "staff", "password": "seller-password"}, client=fresh)[0], 200)
        self.assertEqual(self.call("/api/users", {
            "id": user["id"], "name": "Encargado", "username": "staff", "role": "inventory",
            "active": True, "password": "new-password-123",
        })[0], 200)
        self.assertEqual(self.call("/api/state", client=fresh)[0], 401)
        reset = self.new_client()
        self.assertEqual(self.call("/api/auth/login", {"username": "staff", "password": "new-password-123"}, client=reset)[0], 200)
        self.assertEqual(self.call(f"/api/users/{user['id']}", method="DELETE")[0], 200)
        self.assertNotIn(user["id"], [entry["id"] for entry in self.call("/api/users")[1]])
        self.assertEqual(self.call("/api/auth/login", {"username": "staff", "password": "new-password-123"}, client=self.new_client())[0], 401)

    def test_user_deletion_protects_self_last_admin_and_non_admins(self):
        admin_id = self.admin["user"]["id"]
        self.assertEqual(self.call(f"/api/users/{admin_id}", method="DELETE")[0], 400)
        self.assertEqual(self.call("/api/users", {**self.admin["user"], "role": "seller"})[0], 400)
        second_admin_session = self.new_client()
        self.call("/api/auth/login", {"username": "admin", "password": "test-password-123"}, client=second_admin_session)
        status, updated_admin = self.call("/api/users", {
            **self.admin["user"], "name": "Administración", "username": "admin-new",
        })
        self.assertEqual(status, 200)
        self.assertEqual(updated_admin["username"], "admin-new")
        self.assertEqual(self.call("/api/users")[0], 200)
        self.assertEqual(self.call("/api/users", client=second_admin_session)[0], 401)
        self.assertEqual(self.call("/api/users", {
            **updated_admin, "password": "admin-password-456",
        })[0], 400)
        _, user = self.call("/api/users", {
            "name": "Vendedor", "username": "seller", "password": "seller-password", "role": "seller",
        })
        client = self.new_client()
        self.call("/api/auth/login", {"username": "seller", "password": "seller-password"}, client=client)
        self.assertEqual(self.call(f"/api/users/{user['id']}", method="DELETE", client=client)[0], 403)

    def test_restart_does_not_recreate_deleted_catalog(self):
        with server.connect() as db:
            db.execute("DELETE FROM products")
        server.initialize_database()
        self.assertEqual(server.get_state()["products"], [])

    def backup_fixture(self):
        product = self.product()
        _, supplier = self.call("/api/suppliers", {"name": "Proveedor"})
        self.call("/api/purchases", {"supplierId": supplier["id"], "items": [
            {"productId": product["id"], "quantity": 5, "unitCost": 50},
        ]})
        self.call("/api/sales", {"items": [{"id": product["id"], "quantity": 2}]})
        status, backup = self.call("/api/backup")
        self.assertEqual(status, 200)
        return backup

    def test_backup_roundtrip_and_account_preservation(self):
        backup = self.backup_fixture()
        account = self.call("/api/auth/status")[1]["user"]
        self.assertEqual(backup["version"], 1)
        self.assertNotIn("users", backup)
        expected = server.get_state()
        self.call("/api/products", {"name": "Temporal", "sku": "TEMP", "category": "Test", "price": 1, "min": 0})
        self.assertEqual(self.call("/api/backup/restore", backup)[0], 200)
        snapshots = list((server.DB_PATH.parent / "backups").glob("inventory-before-restore-*.db"))
        self.assertEqual(len(snapshots), 1)
        snapshot = sqlite3.connect(snapshots[0])
        try:
            self.assertEqual(snapshot.execute("SELECT sku FROM products WHERE sku='TEMP'").fetchone(), ("TEMP",))
        finally:
            snapshot.close()
        self.assertEqual(server.get_state(), expected)
        self.assertEqual(self.call("/api/auth/status")[1]["user"], account)
        legacy = {key: value for key, value in backup.items() if key not in ("format", "version")}
        self.assertEqual(self.call("/api/backup/restore", legacy)[0], 200)

    def test_snapshot_retention_keeps_only_ten_recent_files(self):
        folder = server.DB_PATH.parent / "backups"
        folder.mkdir()
        for index in range(10):
            (folder / f"inventory-before-restore-20200101T000000-{index:04d}.db").write_bytes(b"old")
        latest = server.snapshot_database()
        snapshots = list(folder.glob("inventory-before-restore-*.db"))
        self.assertEqual(len(snapshots), 10)
        self.assertIn(latest, snapshots)

    def test_invalid_backups_preserve_all_existing_records(self):
        backup = self.backup_fixture()
        expected = server.get_state()
        invalid = []
        for key in ("products", "suppliers", "sales", "purchases", "movements"):
            missing = deepcopy(backup)
            del missing[key]
            invalid.append(missing)
            malformed = deepcopy(backup)
            malformed[key] = [None]
            invalid.append(malformed)
        for field, value in (("quantity", True), ("quantity", 1.9), ("date", "ayer"), ("saleId", [])):
            modified = deepcopy(backup)
            modified["movements"][0][field] = value
            invalid.append(modified)
        for key, field, value in (
            ("sales", "total", 999), ("purchases", "supplierId", "missing"),
            ("products", "stock", 999), ("products", "name", ""), ("products", "price", True),
        ):
            modified = deepcopy(backup)
            modified[key][0][field] = value
            invalid.append(modified)
        duplicate = deepcopy(backup)
        duplicate["products"].append(duplicate["products"][0])
        invalid.append(duplicate)
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                status, result = self.call("/api/backup/restore", candidate)
                self.assertEqual(status, 400)
                self.assertIn("error", result)
                self.assertEqual(server.get_state(), expected)

    def test_restore_rolls_back_when_database_rejects_an_insert(self):
        backup = self.backup_fixture()
        expected = server.get_state()
        with server.connect() as db:
            db.execute("CREATE TRIGGER reject_sale BEFORE INSERT ON sales BEGIN SELECT RAISE(ABORT, 'test'); END")
        self.assertEqual(self.call("/api/backup/restore", backup)[0], 400)
        self.assertEqual(server.get_state(), expected)

    def test_backup_endpoints_are_admin_only(self):
        for role in ("seller", "inventory"):
            self.call("/api/users", {"name": role, "username": role, "password": "test-password", "role": role})
            client = self.new_client()
            self.call("/api/auth/login", {"username": role, "password": "test-password"}, client=client)
            self.assertEqual(self.call("/api/backup", client=client)[0], 403)
            self.assertEqual(self.call("/api/backup/restore", {}, client=client)[0], 403)
        self.assertEqual(self.call("/api/backup", client=self.new_client())[0], 401)

    def test_empty_backup_and_sales_with_nonsequential_folios(self):
        backup = self.backup_fixture()
        backup["sales"][0]["folio"] = "V-0002"
        backup["purchases"][0]["folio"] = "C-0002"
        self.assertEqual(self.call("/api/backup/restore", backup)[0], 200)
        product_id = backup["sales"][0]["items"][0]["id"]
        self.assertEqual(self.call("/api/sales", {"items": [{"id": product_id, "quantity": 1}]})[0], 201)
        self.assertEqual(self.call("/api/purchases", {"supplierId": backup["suppliers"][0]["id"], "items": [
            {"productId": product_id, "quantity": 1, "unitCost": 50},
        ]})[0], 201)
        for key in ("products", "suppliers", "sales", "purchases", "movements"):
            backup[key] = []
        self.assertEqual(self.call("/api/backup/restore", backup)[0], 200)
        server.initialize_database()
        self.assertTrue(all(not values for values in server.get_state().values()))


if __name__ == "__main__":
    unittest.main()
