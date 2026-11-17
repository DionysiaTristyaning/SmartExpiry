"""Stok masuk, stok keluar, FEFO, dan pencegahan transaksi ganda (SD 5.3, 7, 8.9, 13.2 S1-S8)."""
from datetime import timedelta

import pytest

from app.common.dates import today_jakarta
from tests.conftest import STAFF, STAFF2, batch_of, product, reconcile, rid

TODAY = today_jakarta()


def _stock_in(db, sku="P004", quantity=24, expiry_days=40, received_days_ago=0, **extra):
    body = {"product_id": str(product(db, sku)["_id"]), "quantity": quantity,
            "received_date": (TODAY - timedelta(days=received_days_ago)).isoformat(),
            "expiry_date": (TODAY + timedelta(days=expiry_days)).isoformat(), "client_request_id": rid()}
    body.update(extra)
    return body


def _stock_out(batch, quantity, **extra):
    return {"batch_id": str(batch["_id"]), "quantity": quantity, "client_request_id": rid(), **extra}


# ---------- stok masuk ----------

def test_stock_in_creates_new_batch_with_system_number_and_stock_in(login_as, db):
    c = login_as(STAFF)
    response = c.post("/api/v1/batches", json=_stock_in(db))
    assert response.status_code == 201, response.get_json()
    batch = response.get_json()["data"]
    assert batch["batch_number"].startswith(f"BT-{TODAY:%y%m%d}-")
    assert batch["current_quantity"] == batch["initial_quantity"] == 24
    stored = db.batches.find_one({"batch_number": batch["batch_number"]})
    movement = db.stock_movements.find_one({"batch_id": stored["_id"]})
    assert movement["movement_type"] == "stock_in" and movement["quantity"] == 24
    assert movement["quantity_before"] == 0 and movement["quantity_after"] == 24
    assert movement["created_by"] == db.master_karyawan.find_one({"email": STAFF})["_id"]
    assert movement["source"] == {"type": "manual"}


def test_two_identical_receipts_create_two_batches(login_as, db):
    c = login_as(STAFF)
    first = c.post("/api/v1/batches", json=_stock_in(db)).get_json()["data"]
    second = c.post("/api/v1/batches", json=_stock_in(db)).get_json()["data"]
    assert first["batch_number"] != second["batch_number"]
    assert int(second["batch_number"][-3:]) == int(first["batch_number"][-3:]) + 1


@pytest.mark.parametrize("override,field", [
    ({"expiry_days": 0}, "expiry_date"),          # kedaluwarsa hari ini
    ({"expiry_days": -5}, "expiry_date"),         # sudah lewat
    ({"received_days_ago": -1}, "received_date"),  # tanggal masuk di masa depan
    ({"quantity": 0}, "quantity"),
    ({"quantity": -3}, "quantity"),
    ({"quantity": 100001}, "quantity"),
])
def test_stock_in_validation(login_as, db, override, field):
    response = login_as(STAFF).post("/api/v1/batches", json=_stock_in(db, **override))
    assert response.status_code == 400 and field in response.get_json()["error"]["fields"]


def test_expiry_must_be_after_received_date(login_as, db):
    body = _stock_in(db, expiry_days=1, received_days_ago=0)
    body["received_date"] = body["expiry_date"]
    assert login_as(STAFF).post("/api/v1/batches", json=body).status_code == 400


def test_invalid_date_text_is_rejected(login_as, db):
    assert login_as(STAFF).post("/api/v1/batches", json=_stock_in(db, expiry_date="2026-02-30")).status_code == 400


def test_preview_shows_status_and_saves_nothing(login_as, db):
    before = db.batches.count_documents({})
    response = login_as(STAFF).post("/api/v1/batches/preview", json=_stock_in(db, expiry_days=10))
    data = response.get_json()["data"]
    assert response.status_code == 200 and data["expiry_status"] == "near_expired" and data["remaining_days"] == 10
    assert db.batches.count_documents({}) == before


def test_resubmitting_the_same_form_does_not_duplicate(login_as, db):
    c = login_as(STAFF)
    body = _stock_in(db)
    assert c.post("/api/v1/batches", json=body).status_code == 201
    batches, movements = db.batches.count_documents({}), db.stock_movements.count_documents({})
    assert c.post("/api/v1/batches", json=body).status_code == 409
    assert db.batches.count_documents({}) == batches and db.stock_movements.count_documents({}) == movements


def test_client_request_id_is_required(login_as, db):
    body = _stock_in(db)
    body.pop("client_request_id")
    assert login_as(STAFF).post("/api/v1/batches", json=body).status_code == 400


def test_batch_data_cannot_be_edited(login_as, db):
    batch = batch_of(db, "P004")
    c = login_as(STAFF)
    assert c.put(f"/api/v1/batches/{batch['_id']}", json={"expiry_date": "2030-01-01"}).status_code == 405
    assert c.delete(f"/api/v1/batches/{batch['_id']}").status_code == 405


# ---------- stok keluar ----------

def test_stock_out_without_reason(login_as, db):
    batch = batch_of(db, "P004")
    response = login_as(STAFF).post("/api/v1/movements/stock-out", json=_stock_out(batch, 3))
    assert response.status_code == 201, response.get_json()
    movement = response.get_json()["data"]
    assert movement["movement_type"] == "stock_out" and movement["reason"] is None
    assert movement["quantity_before"] - movement["quantity_after"] == 3
    assert db.batches.find_one({"_id": batch["_id"]})["current_quantity"] == batch["current_quantity"] - 3


def test_stock_out_cannot_exceed_stock(login_as, db):
    batch = batch_of(db, "P004")
    response = login_as(STAFF).post("/api/v1/movements/stock-out", json=_stock_out(batch, batch["current_quantity"] + 1))
    assert response.status_code == 400 and "tersisa" in response.get_json()["error"]["message"]
    assert db.batches.find_one({"_id": batch["_id"]})["current_quantity"] == batch["current_quantity"]


def test_two_stock_outs_cannot_make_stock_negative(login_as, db):
    batch = batch_of(db, "P004")
    qty = batch["current_quantity"]
    a, b = login_as(STAFF), login_as(STAFF2)
    assert a.post("/api/v1/movements/stock-out", json=_stock_out(batch, qty - 1)).status_code == 201
    assert b.post("/api/v1/movements/stock-out", json=_stock_out(batch, 2)).status_code == 400
    assert db.batches.find_one({"_id": batch["_id"]})["current_quantity"] == 1


def test_expired_batch_cannot_be_sold(login_as, db):
    expired = batch_of(db, "P013")  # kedaluwarsa 3 hari lalu
    response = login_as(STAFF).post("/api/v1/movements/stock-out", json=_stock_out(expired, 1))
    assert response.status_code == 400 and "kedaluwarsa" in response.get_json()["error"]["message"]


def _inspect_damaged(c, batch, damaged):
    response = c.post("/api/v1/inspections", json={
        "batch_id": str(batch["_id"]), "physical_quantity": batch["current_quantity"], "product_condition": "rusak",
        "packaging_condition": "baik", "damaged_quantity": damaged, "notes": "Basah kena bocor", "client_request_id": rid()})
    assert response.status_code == 201, response.get_json()


def test_fully_damaged_batch_cannot_be_sold(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    _inspect_damaged(c, batch, batch["current_quantity"])
    response = c.post("/api/v1/movements/stock-out", json=_stock_out(batch, 1))
    assert response.status_code == 400 and "rusak" in response.get_json()["error"]["message"]


def test_fefo_suggests_nearest_sellable_batch(login_as, db):
    pid = product(db, "P001")["_id"]
    items = login_as(STAFF).get(f"/api/v1/batches/fefo?product_id={pid}").get_json()["data"]
    assert [i["expiry_date"] for i in items] == sorted(i["expiry_date"] for i in items)
    assert all(i["sellable"] and i["expiry_status"] != "expired" for i in items)
    # produk yang satu-satunya batch-nya Expired tidak punya batch layak jual
    assert login_as(STAFF).get(f"/api/v1/batches/fefo?product_id={product(db, 'P013')['_id']}").get_json()["data"] == []


def test_movements_cannot_be_edited_or_deleted(login_as, db):
    movement = db.stock_movements.find_one({})
    c = login_as(STAFF)
    assert c.put(f"/api/v1/movements/{movement['_id']}", json={"quantity": 1}).status_code == 405
    assert c.delete(f"/api/v1/movements/{movement['_id']}").status_code == 405


def test_every_movement_has_a_source_and_reconciles(db):
    assert db.stock_movements.count_documents({"source.type": {"$exists": False}}) == 0
    for batch in db.batches.find({}):
        assert reconcile(db, batch["_id"]) == batch["current_quantity"], batch["batch_number"]
    # rantai sebelum/sesudah utuh
    for batch in db.batches.find({}):
        moves = list(db.stock_movements.find({"batch_id": batch["_id"]}).sort([("created_at", 1), ("_id", 1)]))
        for prev, cur in zip(moves, moves[1:]):
            assert prev["quantity_after"] == cur["quantity_before"]


def test_reconciliation_after_many_operations(login_as, db):
    c = login_as(STAFF)
    batch = c.post("/api/v1/batches", json=_stock_in(db, quantity=50)).get_json()["data"]
    bid = db.batches.find_one({"batch_number": batch["batch_number"]})["_id"]
    for qty in (5, 7, 3):
        c.post("/api/v1/movements/stock-out", json={"batch_id": str(bid), "quantity": qty, "client_request_id": rid()})
    c.post("/api/v1/movements/stock-out", json={"batch_id": str(bid), "quantity": 999, "client_request_id": rid()})
    assert db.batches.find_one({"_id": bid})["current_quantity"] == reconcile(db, bid) == 35


def test_movement_list_filters(login_as, db):
    c = login_as(STAFF)
    data = c.get("/api/v1/movements?movement_type=stock_out").get_json()["data"]
    assert data and all(m["movement_type"] == "stock_out" for m in data)
    assert c.get("/api/v1/movements?movement_type=transfer").status_code == 400
    assert c.get(f"/api/v1/movements?date_from={TODAY}&date_to={TODAY - timedelta(days=1)}").status_code == 400


def test_batch_detail_has_history(login_as, db):
    batch = batch_of(db, "P005")
    data = login_as(STAFF).get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]
    assert data["movements"] and data["inspections"] and data["requests"]
    assert data["fitness"] == "partial" and data["sellable"] is True  # 3 dari 12 rusak, 9 masih boleh dijual
    assert data["damaged_quantity"] == 3 and data["sellable_quantity"] == 9


# ---------- barang terjual per produk (rekap harian, otomatis FEFO) ----------

def _sale(db, sku, quantity, **extra):
    return {"product_id": str(product(db, sku)["_id"]), "quantity": quantity, "client_request_id": rid(), **extra}


def test_sale_per_product_takes_nearest_expiry_first_and_splits(login_as, db):
    susu_near, susu_far = sorted(db.batches.find({"product_id": product(db, "P001")["_id"]}),
                                 key=lambda b: b["expiry_date"])
    total = susu_near["current_quantity"] + 5
    response = login_as(STAFF).post("/api/v1/movements/stock-out", json=_sale(db, "P001", total))
    assert response.status_code == 201, response.get_json()
    data = response.get_json()["data"]
    assert [m["batch_number"] for m in data["movements"]] == [susu_near["batch_number"], susu_far["batch_number"]]
    assert [m["quantity"] for m in data["movements"]] == [susu_near["current_quantity"], 5]
    assert db.batches.find_one({"_id": susu_near["_id"]})["current_quantity"] == 0
    assert db.batches.find_one({"_id": susu_far["_id"]})["current_quantity"] == susu_far["current_quantity"] - 5
    assert reconcile(db, susu_far["_id"]) == susu_far["current_quantity"] - 5


def test_sale_never_takes_expired_or_damaged_units(login_as, db):
    c = login_as(STAFF)
    roti = batch_of(db, "P005")       # 12 di stok, 3 rusak -> hanya 9 boleh terjual
    over = c.post("/api/v1/movements/stock-out", json=_sale(db, "P005", 10))
    assert over.status_code == 400 and "hanya 9" in over.get_json()["error"]["message"]
    assert c.post("/api/v1/movements/stock-out", json=_sale(db, "P005", 9)).status_code == 201
    assert db.batches.find_one({"_id": roti["_id"]})["current_quantity"] == 3
    jus = c.post("/api/v1/movements/stock-out", json=_sale(db, "P013", 1))  # satu-satunya batch Expired
    assert jus.status_code == 400 and "hanya 0" in jus.get_json()["error"]["message"]


def test_sale_double_click_is_ignored(login_as, db):
    c = login_as(STAFF)
    body = _sale(db, "P004", 2)
    assert c.post("/api/v1/movements/stock-out", json=body).status_code == 201
    assert c.post("/api/v1/movements/stock-out", json=body).status_code == 409
    assert db.stock_movements.count_documents({"client_request_id": body["client_request_id"]}) == 1


def test_sale_validation(login_as, db):
    c = login_as(STAFF)
    assert c.post("/api/v1/movements/stock-out", json=_sale(db, "P004", 0)).status_code == 400
    assert c.post("/api/v1/movements/stock-out", json={"product_id": "abc", "quantity": 1,
                                                       "client_request_id": rid()}).status_code == 400


# ---------- barang datang: satuan besar dan barang ditolak ----------

def _with_pack(db, sku="P004", unit="karton", size=24):
    db.master_product.update_one({"sku": sku}, {"$set": {"pack_unit": unit, "pack_size": size}})


def test_receipt_in_packs_is_converted_to_small_units(login_as, db):
    _with_pack(db)
    c = login_as(STAFF)
    body = _stock_in(db, quantity=5, pack_quantity=3)
    preview = c.post("/api/v1/batches/preview", json=body).get_json()["data"]
    assert preview["received_quantity"] == 77 and preview["quantity"] == 77
    created = c.post("/api/v1/batches", json=body).get_json()["data"]
    assert created["initial_quantity"] == created["current_quantity"] == 77
    assert created["pack"] == {"unit": "karton", "size": 24, "count": 3, "loose": 5}


def test_packs_only_and_product_without_pack(login_as, db):
    c = login_as(STAFF)
    assert c.post("/api/v1/batches", json=_stock_in(db, "P002", quantity="", pack_quantity=2)).status_code == 400  # tanpa karton
    _with_pack(db)
    created = c.post("/api/v1/batches", json=_stock_in(db, quantity="", pack_quantity=2)).get_json()["data"]
    assert created["current_quantity"] == 48


def test_rejected_on_arrival_does_not_enter_stock(login_as, db):
    c = login_as(STAFF)
    assert c.post("/api/v1/batches", json=_stock_in(db, quantity=24, rejected_quantity=2)).status_code == 400  # alasan wajib
    assert c.post("/api/v1/batches", json=_stock_in(db, quantity=24, rejected_quantity=25,
                                                    reject_reason="Penyok")).status_code == 400
    created = c.post("/api/v1/batches", json=_stock_in(db, quantity=24, rejected_quantity=2,
                                                       reject_reason="Botol penyok")).get_json()["data"]
    assert created["received_quantity"] == 24 and created["rejected_quantity"] == 2
    assert created["initial_quantity"] == created["current_quantity"] == 22
    assert reconcile(db, db.batches.find_one({"batch_number": created["batch_number"]})["_id"]) == 22
    assert db.audit_logs.find_one({"action": "stock_in_recorded", "details.rejected_quantity": 2})


def test_all_rejected_creates_no_batch_but_is_logged(login_as, db):
    c = login_as(STAFF)
    batches = db.batches.count_documents({})
    body = _stock_in(db, quantity=10, rejected_quantity=10, reject_reason="Semua basah kena hujan")
    response = c.post("/api/v1/batches", json=body)
    assert response.status_code == 201 and response.get_json()["data"]["rejected_all"] is True
    assert db.batches.count_documents({}) == batches
    assert db.audit_logs.find_one({"action": "receipt_rejected"})
    assert c.post("/api/v1/batches", json=body).status_code == 409  # klik ganda


# ---------- jadwal cek fisik ----------

def test_check_schedule_rules():
    from datetime import date, datetime, timezone
    from app.modules.expiry.services import check_schedule
    today = date(2026, 11, 14)
    assert check_schedule("critical", 5, "2026-11-13", None, today)["check_due"] is True      # 1 hari
    assert check_schedule("near_expired", 5, "2026-11-12", None, today)["check_due"] is False  # 2 < 3 hari
    assert check_schedule("normal", 5, "2026-11-07", None, today)["check_due"] is True         # 7 hari
    insp = {"inspected_at": datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)}                # = 14 Nov WIB
    assert check_schedule("critical", 5, "2026-10-01", insp, today)["check_due"] is False
    assert check_schedule("expired", 5, "2026-10-01", None, today)["check_due"] is False       # tidak dijadwalkan
    assert check_schedule("normal", 0, "2026-10-01", None, today)["check_due"] is False        # stok habis


def test_check_due_list_and_inspection_clears_it(login_as, db):
    c = login_as(STAFF)
    items = c.get("/api/v1/expiry/alerts?status=check_due&limit=100").get_json()["data"]
    assert items and all(i["check_due"] and i["expiry_status"] != "expired" for i in items)
    ranks = ["critical", "near_expired", "monitoring", "normal"]
    assert [ranks.index(i["expiry_status"]) for i in items] == sorted(ranks.index(i["expiry_status"]) for i in items)
    target = next(i for i in items if i["sku"] == "P004")
    c.post("/api/v1/inspections", json={"batch_id": target["id"], "physical_quantity": target["current_quantity"],
                                        "product_condition": "baik", "packaging_condition": "baik", "client_request_id": rid()})
    after = c.get("/api/v1/expiry/alerts?status=check_due&limit=100").get_json()["data"]
    assert target["id"] not in {i["id"] for i in after}
    assert c.get("/api/v1/dashboard/summary").get_json()["data"]["check_due"] == len(after)



# ---------- tanggal penjualan ----------

def test_sale_date_can_be_backdated_up_to_seven_days(login_as, db):
    c = login_as(STAFF)
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    done = c.post("/api/v1/movements/stock-out", json=_sale(db, "P004", 2, sale_date=yesterday)).get_json()["data"]
    assert done["sale_date"] == yesterday and all(m["movement_date"] == yesterday for m in done["movements"])
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    too_old = (TODAY - timedelta(days=8)).isoformat()
    assert c.post("/api/v1/movements/stock-out", json=_sale(db, "P004", 1, sale_date=tomorrow)).status_code == 400
    assert c.post("/api/v1/movements/stock-out", json=_sale(db, "P004", 1, sale_date=too_old)).status_code == 400


def test_backdated_sale_skips_batches_that_arrived_later(login_as, db):
    c = login_as(STAFF)
    c.post("/api/v1/batches", json=_stock_in(db, "P011", quantity=10, expiry_days=10))  # Saus: batch baru hari ini
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    done = c.post("/api/v1/movements/stock-out", json=_sale(db, "P011", 3, sale_date=yesterday)).get_json()["data"]
    assert all(m["batch_number"] != db.batches.find_one({"received_date": TODAY.isoformat(),
                                                         "product_id": product(db, "P011")["_id"]})["batch_number"]
               for m in done["movements"])
