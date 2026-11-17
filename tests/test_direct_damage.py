"""Laporan barang rusak langsung lewat form Ajukan (17 Nov 2026): jumlahnya DITAHAN selama pengajuan terbuka."""
from tests.conftest import ADMIN, STAFF, STAFF2, SUPERVISOR, batch_of, reconcile, rid

URL = "/api/v1/requests"
NOTE = "Dikembalikan ke PT Sumber Segar, surat jalan retur SJR-0112"


def _submit(c, batch, request_type="return", quantity=2, reason="Kemasan basah", **extra):
    body = {"batch_id": str(batch["_id"]), "request_type": request_type, "quantity": quantity, "reason": reason,
            "client_request_id": rid(), **extra}
    return c.post(URL, json=body)


def _damage(c, batch, quantity=5, request_type="return", **extra):
    return _submit(c, batch, request_type=request_type, quantity=quantity, basis="damaged", **extra)


def _sell(c, batch, quantity):
    return c.post("/api/v1/movements/stock-out", json={"product_id": str(batch["product_id"]), "quantity": quantity,
                                                         "client_request_id": rid()})


def _state(c, batch):
    return c.get(f"/api/v1/batches/{batch['_id']}").get_json()["data"]


def _inspect_damage(c, batch, damaged):
    return c.post("/api/v1/inspections", json={
        "batch_id": str(batch["_id"]), "physical_quantity": batch["current_quantity"], "product_condition": "rusak",
        "packaging_condition": "baik", "damaged_quantity": damaged, "notes": f"{damaged} bungkus basah",
        "client_request_id": rid()})


def test_direct_damage_report_holds_the_quantity_immediately(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")                       # Normal, stok 100, tidak ada rusak tercatat
    before_units = login_as(SUPERVISOR).get("/api/v1/dashboard/summary").get_json()["data"]["damaged_units"]
    response = _damage(c, batch, 5)
    assert response.status_code == 201
    doc = response.get_json()["data"]
    assert doc["basis"] == "damaged" and doc["damage_source"] == "direct" and doc["status"] == "pending"
    state = _state(c, batch)
    assert (state["current_quantity"], state["held_quantity"], state["damaged_quantity"]) == (100, 5, 5)
    assert state["sellable_quantity"] == 95 and state["fitness"] == "partial"      # stok fisik belum berubah
    after = login_as(SUPERVISOR).get("/api/v1/dashboard/summary").get_json()["data"]["damaged_units"]
    assert after == before_units + 5
    assert _sell(c, batch, 96).status_code == 400                                   # yang ditahan tidak bisa dijual
    assert _sell(c, batch, 95).status_code == 201
    assert reconcile(db, batch["_id"]) == 5


def test_direct_damage_report_validation(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    assert _damage(c, batch, batch["current_quantity"] + 1).status_code == 400      # melebihi stok
    assert _damage(c, batch, 0).status_code == 400
    assert _submit(c, batch, basis="damaged", quantity=2, reason="").status_code == 400   # alasan wajib
    assert _submit(c, batch, quantity=2).status_code == 400                         # tanpa memilih "barang rusak": tidak otomatis
    assert _damage(c, batch, 2, request_type="disposal").status_code == 201         # rusak boleh dimusnahkan
    assert _damage(c, batch, 3).status_code == 409                                  # satu terbuka per jenis


def test_rejecting_or_cancelling_releases_the_hold(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    doc = _damage(c, batch, 4).get_json()["data"]
    assert _state(c, batch)["sellable_quantity"] == 96
    assert login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/reject", json={"note": "Masih bagus"}).status_code == 200
    state = _state(c, batch)
    assert state["held_quantity"] == 0 and state["sellable_quantity"] == 100 and state["fitness"] != "partial"

    again = _damage(c, batch, 6).get_json()["data"]                                 # boleh diajukan lagi setelah ditolak
    assert _state(c, batch)["sellable_quantity"] == 94
    assert c.post(f"{URL}/{again['id']}/cancel", json={}).status_code == 200
    assert _state(c, batch)["sellable_quantity"] == 100


def test_completing_a_direct_damage_report_reduces_stock_and_ends_the_hold(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    doc = _damage(c, batch, 5).get_json()["data"]
    login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={})
    assert _state(c, batch)["sellable_quantity"] == 95                              # Disetujui pun masih ditahan
    done = login_as(STAFF2).post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 5, "note": NOTE})
    assert done.status_code == 200, done.get_json()
    state = _state(c, batch)
    assert (state["current_quantity"], state["held_quantity"], state["damaged_quantity"], state["sellable_quantity"]) \
        == (95, 0, 0, 95)
    assert reconcile(db, batch["_id"]) == 95
    request_id = db.handling_requests.find_one({"request_number": doc["request_number"]})["_id"]
    movement = db.stock_movements.find_one({"source.handling_request_id": request_id})
    assert movement["source"]["basis"] == "damaged" and movement["quantity"] == 5


def test_partial_completion_releases_the_rest_for_sale(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    doc = _damage(c, batch, 5).get_json()["data"]
    login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={})
    login_as(STAFF2).post(f"{URL}/{doc['id']}/complete",
                          json={"handled_quantity": 3, "note": "Hanya 3 yang rusak, sisanya masih bagus"})
    state = _state(c, batch)
    assert state["current_quantity"] == 97 and state["held_quantity"] == 0 and state["sellable_quantity"] == 97


def test_recorded_damage_keeps_the_fixed_option_and_blocks_direct_amounts(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    assert _inspect_damage(c, batch, 4).status_code == 201
    options = _state(c, batch)["request_options"]
    assert options == [{"basis": "damaged", "quantity": 4, "fixed": True, "types": ["return", "disposal"]}]
    assert _damage(c, batch, 2).status_code == 400                                  # rusak tercatat harus diajukan sekaligus (4)
    created = _damage(c, batch, 4)
    assert created.status_code == 201 and created.get_json()["data"]["damage_source"] == "inspection"


def test_inspection_after_a_direct_report_does_not_double_count(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")
    _damage(c, batch, 3)
    assert _inspect_damage(c, batch, 3).status_code == 201
    state = _state(c, batch)
    assert state["damaged_quantity"] == 3 and state["sellable_quantity"] == 97      # bukan 6 dan 94


def test_hold_leaves_room_for_a_near_expiry_return(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P009")                       # Critical (14 hari), stok 40
    assert _damage(c, batch, 5).status_code == 201
    options = {o["basis"]: o for o in _state(c, batch)["request_options"]}
    assert options["near_expiry"]["quantity"] == 35 and options["damaged"]["blocked_by"]
    assert _submit(c, batch, quantity=36, basis="near_expiry").status_code == 400
    ret = _submit(c, batch, quantity=35, basis="near_expiry")
    assert ret.status_code == 201
    request_id = ret.get_json()["data"]["id"]
    login_as(SUPERVISOR).post(f"{URL}/{request_id}/approve", json={})
    done = login_as(STAFF2).post(f"{URL}/{request_id}/complete", json={"handled_quantity": 35, "note": NOTE})
    assert done.status_code == 200, done.get_json()
    state = _state(c, batch)
    assert (state["current_quantity"], state["held_quantity"], state["sellable_quantity"]) == (5, 5, 0)


def test_expired_batch_still_offers_only_the_whole_batch(login_as, db):
    options = _state(login_as(STAFF), batch_of(db, "P013"))["request_options"]
    assert [o["basis"] for o in options] == ["expired"]


def test_only_staff_can_report_damage(login_as, db):
    batch = batch_of(db, "P004")
    assert _damage(login_as(SUPERVISOR), batch, 2).status_code == 403
    assert _damage(login_as(ADMIN), batch, 2).status_code == 403
