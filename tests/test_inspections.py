"""Pemeriksaan fisik dan penyesuaian stok dari hasil pemeriksaan (SD 5.3 C, 5.5 A, 13.3 I1-I2, 13.4 H2, H12-H13)."""
import pytest

from tests.conftest import ADMIN, STAFF, STAFF2, SUPERVISOR, SUPERVISOR2, batch_of, reconcile, rid

URL = "/api/v1/inspections"


def _body(batch, physical, product="baik", packaging="baik", notes="", damaged=None, **extra):
    if damaged is None:  # bila rusak tanpa jumlah: anggap semua barang yang dihitung rusak
        damaged = physical if "rusak" in (product, packaging) else 0
    return {"batch_id": str(batch["_id"]), "physical_quantity": physical, "product_condition": product,
            "packaging_condition": packaging, "damaged_quantity": damaged, "notes": notes,
            "client_request_id": rid(), **extra}


@pytest.mark.parametrize("email", [STAFF, SUPERVISOR])
def test_staff_and_supervisor_can_inspect_without_changing_stock(login_as, db, email):
    batch = batch_of(db, "P004")
    movements = db.stock_movements.count_documents({})
    response = login_as(email).post(URL, json=_body(batch, batch["current_quantity"]))
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["system_quantity"] == batch["current_quantity"] and data["difference"] == 0 and data["is_fit"]
    assert db.stock_movements.count_documents({}) == movements
    assert db.batches.find_one({"_id": batch["_id"]})["current_quantity"] == batch["current_quantity"]


def test_notes_required_for_difference_or_damage(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    assert c.post(URL, json=_body(batch, batch["current_quantity"] - 1)).status_code == 400
    assert c.post(URL, json=_body(batch, batch["current_quantity"], packaging="rusak")).status_code == 400
    assert c.post(URL, json=_body(batch, batch["current_quantity"], packaging="rusak", notes="Penyok")).status_code == 201


def test_condition_values_are_validated(login_as, db):
    batch = batch_of(db, "P004")
    assert login_as(STAFF).post(URL, json=_body(batch, 1, product="good")).status_code == 400
    assert login_as(STAFF).post(URL, json=_body(batch, -1)).status_code == 400


def test_each_inspection_is_a_new_record(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    before = db.inspections.count_documents({"batch_id": batch["_id"]})
    c.post(URL, json=_body(batch, batch["current_quantity"]))
    c.post(URL, json=_body(batch, batch["current_quantity"], product="rusak", notes="Basah"))
    assert db.inspections.count_documents({"batch_id": batch["_id"]}) == before + 2
    detail = c.get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]
    assert detail["fitness"] == "unfit"  # kelayakan mengikuti pemeriksaan TERAKHIR
    c.post(URL, json=_body(batch, batch["current_quantity"]))
    assert c.get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]["fitness"] == "fit"


# ---------- penyesuaian ----------

def _inspect_with_difference(c, db, sku="P004", diff=-2):
    batch = batch_of(db, sku)
    response = c.post(URL, json=_body(batch, batch["current_quantity"] + diff, notes="Selisih hitung"))
    assert response.status_code == 201
    return batch, response.get_json()["data"]


def test_staff_adjusts_stock_directly_from_inspection(login_as, db):
    c = login_as(STAFF)
    batch, inspection = _inspect_with_difference(c, db, diff=-2)
    assert inspection["adjustment_status"] == "available"
    response = c.post(f"{URL}/{inspection['id']}/adjust", json={})
    assert response.status_code == 201, response.get_json()
    movement = response.get_json()["data"]
    assert movement["movement_type"] == "adjustment_out" and movement["quantity"] == 2
    stored = db.stock_movements.find_one({"source.type": "inspection", "batch_id": batch["_id"]})
    assert str(stored["source"]["inspection_id"]) == inspection["id"]
    after = db.batches.find_one({"_id": batch["_id"]})["current_quantity"]
    assert after == batch["current_quantity"] - 2 == reconcile(db, batch["_id"])
    assert c.get(f"{URL}/{inspection['id']}").get_json()["data"]["adjustment_status"] == "adjusted"


def test_adjustment_up(login_as, db):
    c = login_as(STAFF)
    batch, inspection = _inspect_with_difference(c, db, diff=3)
    movement = c.post(f"{URL}/{inspection['id']}/adjust", json={}).get_json()["data"]
    assert movement["movement_type"] == "adjustment_in" and movement["quantity"] == 3


def test_one_adjustment_per_inspection(login_as, db):
    c = login_as(STAFF)
    _, inspection = _inspect_with_difference(c, db)
    assert c.post(f"{URL}/{inspection['id']}/adjust", json={}).status_code == 201
    assert login_as(STAFF2).post(f"{URL}/{inspection['id']}/adjust", json={}).status_code == 409


def test_stale_inspection_cannot_be_used(login_as, db):
    c = login_as(STAFF)
    batch, inspection = _inspect_with_difference(c, db)
    c.post("/api/v1/movements/stock-out", json={"batch_id": str(batch["_id"]), "quantity": 1, "client_request_id": rid()})
    assert c.get(f"{URL}/{inspection['id']}").get_json()["data"]["adjustment_status"] == "stale"
    response = c.post(f"{URL}/{inspection['id']}/adjust", json={})
    assert response.status_code == 409 and "pemeriksaan ulang" in response.get_json()["error"]["message"]


def test_no_adjustment_without_difference(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    inspection = c.post(URL, json=_body(batch, batch["current_quantity"])).get_json()["data"]
    assert c.post(f"{URL}/{inspection['id']}/adjust", json={}).status_code == 400


def test_staff_can_adjust_from_supervisor_inspection(login_as, db):
    _, inspection = _inspect_with_difference(login_as(SUPERVISOR), db)
    assert login_as(SUPERVISOR).post(f"{URL}/{inspection['id']}/adjust", json={}).status_code == 403
    assert login_as(ADMIN).post(f"{URL}/{inspection['id']}/adjust", json={}).status_code == 403
    assert login_as(STAFF).post(f"{URL}/{inspection['id']}/adjust", json={}).status_code == 201


def test_adjustment_is_audited(login_as, db):
    c = login_as(STAFF)
    _, inspection = _inspect_with_difference(c, db)
    c.post(f"{URL}/{inspection['id']}/adjust", json={})
    assert db.audit_logs.count_documents({"action": "stock_adjusted"}) >= 2  # 1 dari seed + 1 di sini


def test_list_filters(login_as):
    c = login_as(STAFF)
    unfit = c.get(f"{URL}?fitness=unfit").get_json()["data"]
    assert unfit and all(not i["is_fit"] for i in unfit)
    diffs = c.get(f"{URL}?has_difference=true").get_json()["data"]
    assert diffs and all(i["difference"] != 0 for i in diffs)


def test_resubmitting_the_same_inspection_form_is_ignored(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    body = _body(batch, batch["current_quantity"])
    before = db.inspections.count_documents({})
    assert c.post(URL, json=body).status_code == 201
    assert c.post(URL, json=body).status_code == 409
    assert db.inspections.count_documents({}) == before + 1
    body.pop("client_request_id")
    assert c.post(URL, json=body).status_code == 400


# ---------- barang rusak sebagian (standar ritel: dipisah per buah) ----------

def test_damaged_quantity_is_required_and_limited(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    qty = batch["current_quantity"]
    body = _body(batch, qty, packaging="rusak", notes="Penyok")
    body.pop("damaged_quantity")
    assert c.post(URL, json=body).status_code == 400                                   # jumlah rusak wajib
    assert c.post(URL, json=_body(batch, qty, packaging="rusak", notes="x", damaged=qty + 1)).status_code == 400
    assert c.post(URL, json=_body(batch, qty, damaged=2)).status_code == 400            # baik tapi ada rusak
    assert c.post(URL, json=_body(batch, 0, packaging="rusak", notes="Tidak ada", damaged=1)).status_code == 400


def test_only_damaged_units_are_blocked_the_rest_can_be_sold(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    qty = batch["current_quantity"]
    assert c.post(URL, json=_body(batch, qty, packaging="rusak", notes="2 bungkus sobek", damaged=2)).status_code == 201
    data = c.get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]
    assert data["fitness"] == "partial" and data["damaged_quantity"] == 2 and data["sellable_quantity"] == qty - 2
    # barang rusak tidak ikut terjual
    over = c.post("/api/v1/movements/stock-out", json={"batch_id": str(batch["_id"]), "quantity": qty - 1,
                                                       "client_request_id": rid()})
    assert over.status_code == 400
    ok = c.post("/api/v1/movements/stock-out", json={"batch_id": str(batch["_id"]), "quantity": qty - 2,
                                                     "client_request_id": rid()})
    assert ok.status_code == 201
    left = c.get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]
    assert left["current_quantity"] == 2 and left["sellable_quantity"] == 0 and left["fitness"] == "unfit"


def test_damaged_units_become_request_option_with_fixed_quantity(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")  # Normal, belum ada rusak tercatat: hanya laporan rusak langsung (jumlah bebas)
    before = c.get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]["request_options"]
    assert before == [{"basis": "damaged", "quantity": batch["current_quantity"], "fixed": False, "direct": True,
                       "types": ["return", "disposal"]}]
    c.post(URL, json=_body(batch, batch["current_quantity"], product="rusak", notes="Basah", damaged=3))
    options = c.get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]["request_options"]
    assert options == [{"basis": "damaged", "quantity": 3, "fixed": True, "types": ["return", "disposal"]}]


# ---------- tanggal di kemasan berbeda -> usulan koreksi, diputuskan Supervisor ----------

def _propose(c, batch, new_date, notes="Tanggal di kemasan berbeda"):
    return c.post(URL, json=_body(batch, batch["current_quantity"], notes=notes, expiry_label="different",
                                  label_expiry_date=new_date))


def test_expiry_label_mismatch_needs_supervisor_approval(login_as, db):
    from app.common.dates import today_jakarta
    from datetime import timedelta
    batch = batch_of(db, "P004")
    new_date = (today_jakarta() + timedelta(days=5)).isoformat()
    created = _propose(login_as(STAFF), batch, new_date)
    assert created.status_code == 201
    inspection = created.get_json()["data"]
    assert inspection["expiry_correction"]["status"] == "pending"
    # tanggal batch belum berubah sebelum disetujui
    assert db.batches.find_one({"_id": batch["_id"]})["expiry_date"] == batch["expiry_date"]
    url = f"{URL}/{inspection['id']}/expiry-correction"
    assert login_as(STAFF).post(url + "/approve", json={}).status_code == 403
    assert login_as(ADMIN).post(url + "/approve", json={}).status_code == 403
    assert login_as(SUPERVISOR).post(url + "/approve", json={"note": "Sudah dicek"}).status_code == 200
    after = db.batches.find_one({"_id": batch["_id"]})
    assert after["expiry_date"] == new_date and after["expiry_history"][0]["old_date"] == batch["expiry_date"]
    status = login_as(STAFF).get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]["expiry_status"]
    assert status == "critical"
    assert db.audit_logs.find_one({"action": "expiry_corrected"})
    assert login_as(SUPERVISOR2).post(url + "/approve", json={}).status_code == 409  # hanya sekali


def test_expiry_correction_rules(login_as, db):
    batch = batch_of(db, "P004")
    c = login_as(STAFF)
    assert _propose(c, batch, batch["expiry_date"]).status_code == 400           # sama dengan yang tercatat
    assert _propose(c, batch, "2026-02-30").status_code == 400                   # bukan tanggal
    assert _propose(c, batch, "2030-01-01", notes="").status_code == 400         # catatan wajib
    first = _propose(c, batch, "2030-01-01").get_json()["data"]
    assert _propose(c, batch, "2030-02-01").status_code == 409                   # satu usulan menunggu per batch
    url = f"{URL}/{first['id']}/expiry-correction"
    assert login_as(SUPERVISOR).post(url + "/reject", json={}).status_code == 400  # alasan tolak wajib
    assert login_as(SUPERVISOR).post(url + "/reject", json={"note": "Kemasan sudah dicek ulang, tanggal benar"}).status_code == 200
    assert db.batches.find_one({"_id": batch["_id"]})["expiry_date"] == batch["expiry_date"]


def test_supervisor_cannot_approve_own_correction(login_as, db):
    batch = batch_of(db, "P004")
    c = login_as(SUPERVISOR)
    inspection = _propose(c, batch, "2030-01-01").get_json()["data"]
    response = c.post(f"{URL}/{inspection['id']}/expiry-correction/approve", json={})
    assert response.status_code == 403
