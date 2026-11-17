import uuid

import mongomock
import pytest

from app import create_app
from app.indexes import ensure_indexes
from seed import PASSWORDS, seed_operations, seed_products, seed_users


@pytest.fixture
def db():
    database = mongomock.MongoClient()["test_db"]
    ensure_indexes(database, skip_text=True)
    seed_users(database)
    seed_products(database)
    seed_operations(database)
    return database


@pytest.fixture
def app(db):
    return create_app({"TESTING": True, "SECRET_KEY": "kunci-untuk-tes-" + "x" * 32, "WTF_CSRF_ENABLED": False}, db=db)


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, email, password=None):
    if password is None:  # akun demo: password masing-masing dari seed.py
        password = PASSWORDS[email]
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.fixture
def login_as(app):
    """Buat klien baru yang sudah login sebagai email tertentu."""
    def _login(email):
        c = app.test_client()
        response = login(c, email)
        assert response.status_code == 200, response.get_json()
        return c
    return _login


STAFF = "rudistaff@gmail.com"
STAFF2 = "rinastaff@gmail.com"
SUPERVISOR = "andisupervisor@gmail.com"
SUPERVISOR2 = "sarisupervisor@gmail.com"
ADMIN = "budiadmin@gmail.com"


def rid():
    """client_request_id baru (dibuat browser setiap kali form dibuka)."""
    return str(uuid.uuid4())


def product(db, sku):
    return db.master_product.find_one({"sku": sku})


def batch_of(db, sku, expiry_days=None):
    """Batch pertama dari produk tertentu (opsional: dengan sisa hari tertentu)."""
    from datetime import timedelta

    from app.common.dates import today_jakarta
    query = {"product_id": product(db, sku)["_id"]}
    if expiry_days is not None:
        query["expiry_date"] = (today_jakarta() + timedelta(days=expiry_days)).isoformat()
    return db.batches.find_one(query, sort=[("expiry_date", 1)])


def reconcile(db, batch_id):
    """Stok batch harus sama dengan jumlah seluruh pergerakannya (SD 8.9)."""
    total = 0
    for m in db.stock_movements.find({"batch_id": batch_id}):
        total += m["quantity"] if m["movement_type"] in ("stock_in", "adjustment_in") else -m["quantity"]
    return total
