"""Impor CSV (SD 9, 13.5 C1-C5)."""
import io
from datetime import timedelta

import pytest

from app.common.dates import today_jakarta
from tests.conftest import ADMIN, STAFF, SUPERVISOR

TODAY = today_jakarta()
FUTURE = (TODAY + timedelta(days=60)).isoformat()


def _post(c, kind, step, text, name="data.csv"):
    return c.post(f"/api/v1/imports/{kind}/{step}", content_type="multipart/form-data",
                  data={"file": (io.BytesIO(text.encode("utf-8")), name)})


PRODUCTS_OK = "sku,name,category,unit,price,description\nP201,Teh Melati,Minuman,botol,4500,\nP202,Kacang,Makanan,pcs,7000,Asin\n"
STOCK_OK = f"sku,quantity,received_date,expiry_date\nP001,10,{TODAY},{FUTURE}\nP002,5,{TODAY},{FUTURE}\n"


# ---------- produk ----------

@pytest.mark.parametrize("email", [SUPERVISOR, ADMIN])
def test_product_import_preview_then_confirm(login_as, db, email):
    c = login_as(email)
    preview = _post(c, "products", "preview", PRODUCTS_OK).get_json()["data"]
    assert preview["valid_rows"] == 2 and preview["applied"] is False
    assert db.master_product.count_documents({"sku": {"$in": ["P201", "P202"]}}) == 0
    done = _post(c, "products", "confirm", PRODUCTS_OK).get_json()["data"]
    assert done["applied"] is True and done["imported"] == 2
    assert db.master_product.find_one({"sku": "P201"})["price"] == 4500


def test_product_import_is_strict(login_as, db):
    text = PRODUCTS_OK + "P001,Sudah Ada,Minuman,pcs,1000,\nP203,Harga Salah,Minuman,pcs,1.000,\nP201,Ganda,X,pcs,1,\n"
    report = _post(login_as(SUPERVISOR), "products", "confirm", text).get_json()["data"]
    assert report["applied"] is False and report["invalid_rows"] == 3
    messages = " ".join(e["message"] for e in report["errors"])
    assert "sudah ada" in messages and "ganda" in messages.lower()
    assert db.master_product.count_documents({"sku": {"$in": ["P201", "P202", "P203"]}}) == 0


def test_staff_cannot_import_products(login_as):
    assert _post(login_as(STAFF), "products", "preview", PRODUCTS_OK).status_code == 403


# ---------- stok awal ----------

def test_stock_import_creates_batches_and_stock_in(login_as, db):
    c = login_as(STAFF)
    batches = db.batches.count_documents({})
    assert _post(c, "stock", "preview", STOCK_OK).get_json()["data"]["valid_rows"] == 2
    assert db.batches.count_documents({}) == batches
    done = _post(c, "stock", "confirm", STOCK_OK).get_json()["data"]
    assert done["imported"] == 2 and db.batches.count_documents({}) == batches + 2
    imported = list(db.stock_movements.find({"source.type": "csv_import"}))
    assert len(imported) == 2 and all(m["movement_type"] == "stock_in" for m in imported)
    numbers = [db.batches.find_one({"_id": m["batch_id"]})["batch_number"] for m in imported]
    assert len(set(numbers)) == 2


def test_same_file_cannot_be_imported_twice(login_as, db):
    c = login_as(STAFF)
    assert _post(c, "stock", "confirm", STOCK_OK).get_json()["data"]["applied"] is True
    response = _post(c, "stock", "confirm", STOCK_OK)
    assert response.status_code == 409 and "sudah pernah dimasukkan" in response.get_json()["error"]["message"]
    assert db.stock_movements.count_documents({"source.type": "csv_import"}) == 2


@pytest.mark.parametrize("row,expected", [
    ("P999,10,{t},{f}", "belum terdaftar"),
    ("P001,0,{t},{f}", "Jumlah"),
    ("P001,abc,{t},{f}", "Jumlah"),
    ("P001,10,{t},2026-02-30", "tanggal"),
    ("P001,10,{t},{t}", "kedaluwarsa"),
    ("P001,10,{f},{f}", "masa depan"),
])
def test_stock_row_errors_block_everything(login_as, db, row, expected):
    text = STOCK_OK + row.format(t=TODAY, f=FUTURE) + "\n"
    batches = db.batches.count_documents({})
    report = _post(login_as(STAFF), "stock", "confirm", text).get_json()["data"]
    assert report["applied"] is False and report["invalid_rows"] == 1
    assert expected.lower() in report["errors"][0]["message"].lower()
    assert db.batches.count_documents({}) == batches


def test_identical_rows_in_one_file_are_rejected(login_as):
    text = f"sku,quantity,received_date,expiry_date\nP001,10,{TODAY},{FUTURE}\nP001,4,{TODAY},{FUTURE}\n"
    report = _post(login_as(STAFF), "stock", "preview", text).get_json()["data"]
    assert report["invalid_rows"] == 1 and "sama persis" in report["errors"][0]["message"]


def test_supervisor_cannot_import_stock(login_as):
    assert _post(login_as(SUPERVISOR), "stock", "preview", STOCK_OK).status_code == 403


@pytest.mark.parametrize("text,name,expected", [
    ("", "a.csv", "kosong"),
    ("sku,quantity\nP001,1\n", "a.csv", "kolom yang kurang"),
    ("sku,quantity,received_date,expiry_date,harga\n", "a.csv", "tidak dikenal"),
    ("sku,sku,received_date,expiry_date\n", "a.csv", "ganda"),
    ("sku,quantity,received_date,expiry_date\n", "a.csv", "belum ada datanya"),
    ("x", "a.txt", ".csv"),
])
def test_file_level_errors(login_as, text, name, expected):
    response = _post(login_as(STAFF), "stock", "preview", text, name)
    assert response.status_code == 400 and expected in response.get_json()["error"]["message"]


def test_oversized_file_is_rejected(login_as):
    big = "sku,quantity,received_date,expiry_date\n" + ("P001,1,2026-01-01,2027-01-01\n" * 40000)
    response = _post(login_as(STAFF), "stock", "preview", big)
    assert response.status_code in (400, 413)


def test_templates_download(login_as):
    c = login_as(STAFF)
    assert c.get("/api/v1/imports/templates/stock").data.decode("utf-8-sig").startswith("sku,quantity,")
    assert c.get("/api/v1/imports/templates/products").data.decode("utf-8-sig").startswith("sku,name,")
    assert c.get("/api/v1/imports/templates/other").status_code == 404


# ---------- rekap penjualan harian ----------

def test_sales_import_preview_then_confirm(login_as, db):
    c = login_as(STAFF)
    text = "sku,quantity\nP001,12\nP004,30\n"
    susu_before = sum(b["current_quantity"] for b in db.batches.find({"product_id": db.master_product.find_one({"sku": "P001"})["_id"]}))
    preview = _post(c, "sales", "preview", text).get_json()["data"]
    assert preview["valid_rows"] == 2 and preview["applied"] is False and "BT-" in preview["preview"][0]["batches"]
    done = _post(c, "sales", "confirm", text).get_json()["data"]
    assert done["applied"] is True and done["imported"] == 2
    susu_after = sum(b["current_quantity"] for b in db.batches.find({"product_id": db.master_product.find_one({"sku": "P001"})["_id"]}))
    assert susu_before - susu_after == 12
    assert _post(c, "sales", "confirm", text).status_code == 409  # file yang sama tidak bisa dua kali


def test_sales_import_is_strict(login_as, db):
    movements = db.stock_movements.count_documents({})
    text = "sku,quantity\nP001,2\nP013,1\nP999,1\nP001,3\nP004,abc\n"
    report = _post(login_as(STAFF), "sales", "confirm", text).get_json()["data"]
    assert report["applied"] is False and report["invalid_rows"] == 4
    messages = " ".join(e["message"] for e in report["errors"])
    assert "hanya 0" in messages and "belum terdaftar" in messages and "Gabungkan" in messages
    assert db.stock_movements.count_documents({}) == movements


def test_only_staff_imports_sales(login_as):
    assert _post(login_as(SUPERVISOR), "sales", "preview", "sku,quantity\nP001,1\n").status_code == 403
    assert login_as(STAFF).get("/api/v1/imports/templates/sales").status_code == 200



def test_sales_import_with_sale_date(login_as, db):
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    text = f"sku,quantity,sale_date\nP001,2,{yesterday}\nP004,1,2020-01-01\n"
    report = _post(login_as(STAFF), "sales", "preview", text).get_json()["data"]
    assert report["invalid_rows"] == 1 and "7 hari" in report["errors"][0]["message"]
