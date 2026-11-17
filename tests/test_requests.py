"""Pengajuan retur/pemusnahan dengan persetujuan Supervisor (SD 5.5 C, 7, 13.4)."""
import pytest

from tests.conftest import ADMIN, STAFF, STAFF2, SUPERVISOR, SUPERVISOR2, batch_of, reconcile, rid

URL = "/api/v1/requests"
NOTE = "Diretur ke PT Sumber Segar, surat jalan retur SJR-0112"


def _submit(c, batch, request_type="return", quantity=2, reason="Kedaluwarsa", **extra):
    body = {"batch_id": str(batch["_id"]), "request_type": request_type, "quantity": quantity, "reason": reason,
            "client_request_id": rid(), **extra}
    return c.post(URL, json=body)


def _new(login_as, db, sku="P009", **kw):
    response = _submit(login_as(STAFF), batch_of(db, sku), **kw)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def test_submit_starts_pending_and_does_not_touch_stock(login_as, db):
    batch = batch_of(db, "P009")
    movements = db.stock_movements.count_documents({})
    doc = _new(login_as, db)
    assert doc["status"] == "pending" and doc["request_number"].startswith("PG-")
    assert [h["action"] for h in doc["history"]] == ["submitted"]
    assert db.stock_movements.count_documents({}) == movements
    assert db.batches.find_one({"_id": batch["_id"]})["current_quantity"] == batch["current_quantity"]


def test_full_flow_return_creates_exactly_one_stock_out(login_as, db):
    batch = batch_of(db, "P009")
    doc = _new(login_as, db, request_type="return", quantity=5)
    assert login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={"note": ""}).status_code == 200
    response = login_as(STAFF2).post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 5, "note": NOTE})  # Staff lain
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["status"] == "completed" and data["handled_quantity"] == 5 and data["completed_by_name"] == "Rina"
    movement = db.stock_movements.find_one({"source.type": "handling_request", "batch_id": batch["_id"]})
    assert movement["movement_type"] == "stock_out" and movement["quantity"] == 5
    assert movement["_id"] == db.handling_requests.find_one({"request_number": doc["request_number"]})["stock_movement_id"]
    assert db.batches.find_one({"_id": batch["_id"]})["current_quantity"] == batch["current_quantity"] - 5
    assert reconcile(db, batch["_id"]) == batch["current_quantity"] - 5
    assert [h["action"] for h in data["history"]] == ["submitted", "approved", "completed"]


def test_double_complete_creates_one_movement(login_as, db):
    doc = _new(login_as, db)
    login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={})
    c = login_as(STAFF)
    assert c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 2, "note": NOTE}).status_code == 200
    assert c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 2}).status_code == 409
    assert db.stock_movements.count_documents({"source.handling_request_id": db.handling_requests.find_one(
        {"request_number": doc["request_number"]})["_id"]}) == 1


def test_partial_completion_needs_note(login_as, db):
    doc = _new(login_as, db, quantity=4)
    login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={})
    c = login_as(STAFF)
    assert c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 3}).status_code == 400
    assert c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 5, "note": "x"}).status_code == 400
    assert c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 3, "note": "1 unit hilang"}).status_code == 200


def test_completion_cannot_exceed_current_stock_and_rolls_back(login_as, db):
    batch = batch_of(db, "P009")
    doc = _new(login_as, db, quantity=batch["current_quantity"])
    login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={})
    c = login_as(STAFF)
    c.post("/api/v1/movements/stock-out", json={"batch_id": str(batch["_id"]), "quantity": 1, "client_request_id": rid()})
    response = c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": batch["current_quantity"], "note": NOTE})
    assert response.status_code == 400
    assert db.handling_requests.find_one({"request_number": doc["request_number"]})["status"] == "approved"


def test_reject_requires_note_and_is_final(login_as, db):
    doc = _new(login_as, db)
    s = login_as(SUPERVISOR)
    assert s.post(f"{URL}/{doc['id']}/reject", json={"note": ""}).status_code == 400
    assert s.post(f"{URL}/{doc['id']}/reject", json={"note": "Barang masih layak"}).status_code == 200
    assert s.post(f"{URL}/{doc['id']}/approve", json={}).status_code == 409
    assert login_as(SUPERVISOR2).post(f"{URL}/{doc['id']}/approve", json={}).status_code == 409
    # setelah ditolak, Staff boleh mengajukan lagi untuk batch dan jenis yang sama
    assert _submit(login_as(STAFF), batch_of(db, "P009")).status_code == 201


def test_decision_only_once(login_as, db):
    doc = _new(login_as, db)
    assert login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={}).status_code == 200
    assert login_as(SUPERVISOR2).post(f"{URL}/{doc['id']}/reject", json={"note": "x"}).status_code == 409


def test_cannot_complete_before_approval(login_as, db):
    doc = _new(login_as, db)
    assert login_as(STAFF).post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 2}).status_code == 409


def test_one_open_request_per_batch_and_basis(login_as, db):
    _new(login_as, db, request_type="return")
    assert _submit(login_as(STAFF2), batch_of(db, "P009"), request_type="return").status_code == 409
    # batch Expired (Jus) sudah punya pemusnahan terbuka dari seed: satu batch Expired = satu penanganan
    expired = batch_of(db, "P013")
    assert _submit(login_as(STAFF2), expired, request_type="disposal", quantity=expired["current_quantity"]).status_code == 409
    assert _submit(login_as(STAFF2), expired, request_type="return", quantity=expired["current_quantity"]).status_code == 409


@pytest.mark.parametrize("override", [{"quantity": 0}, {"quantity": 10_000}, {"reason": ""},
                                      {"request_type": "discount"}, {"request_type": "adjustment"}])
def test_submit_validation(login_as, db, override):
    assert _submit(login_as(STAFF), batch_of(db, "P009"), **override).status_code == 400


def test_duplicate_submission_is_ignored(login_as, db):
    c = login_as(STAFF)
    body = {"batch_id": str(batch_of(db, "P009")["_id"]), "request_type": "return", "quantity": 1, "reason": "x",
            "client_request_id": rid()}
    assert c.post(URL, json=body).status_code == 201
    assert c.post(URL, json=body).status_code == 409


# ---------- pembatalan ----------

def test_submitter_cancels_pending_but_other_staff_cannot(login_as, db):
    doc = _new(login_as, db)
    assert login_as(STAFF2).post(f"{URL}/{doc['id']}/cancel", json={}).status_code == 403
    assert login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/cancel", json={"note": "x"}).status_code == 403
    response = login_as(STAFF).post(f"{URL}/{doc['id']}/cancel", json={})
    assert response.status_code == 200 and response.get_json()["data"]["status"] == "cancelled"


def test_supervisor_cancels_approved_with_reason(login_as, db):
    doc = _new(login_as, db)
    s = login_as(SUPERVISOR)
    s.post(f"{URL}/{doc['id']}/approve", json={})
    assert login_as(STAFF).post(f"{URL}/{doc['id']}/cancel", json={}).status_code == 403
    assert s.post(f"{URL}/{doc['id']}/cancel", json={"note": ""}).status_code == 400
    assert s.post(f"{URL}/{doc['id']}/cancel", json={"note": "Tidak jadi, barang ternyata baik"}).status_code == 200
    assert login_as(STAFF).post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 2}).status_code == 409


def test_closed_requests_cannot_be_cancelled(login_as, db):
    completed = db.handling_requests.find_one({"status": "completed"})
    assert login_as(SUPERVISOR).post(f"{URL}/{completed['_id']}/cancel", json={"note": "x"}).status_code == 409


def test_cancel_and_reject_never_change_stock(login_as, db):
    before = db.stock_movements.count_documents({})
    a = _new(login_as, db, request_type="return")
    b = _new(login_as, db, sku="P003", request_type="return")  # Teh botol, Critical dan layak
    login_as(STAFF).post(f"{URL}/{a['id']}/cancel", json={})
    login_as(SUPERVISOR).post(f"{URL}/{b['id']}/reject", json={"note": "Tidak perlu"})
    assert db.stock_movements.count_documents({}) == before


def test_self_approval_guard_in_service(db):
    from app.common.errors import Forbidden
    from app.modules.requests import services
    supervisor = db.master_karyawan.find_one({"email": SUPERVISOR})
    pending = db.handling_requests.find_one({"status": "pending"})
    db.handling_requests.update_one({"_id": pending["_id"]}, {"$set": {"submitted_by": supervisor["_id"]}})
    with pytest.raises(Forbidden):
        services.review(db, supervisor, pending["_id"], "approve", {})


def test_history_and_filters(login_as, db):
    c = login_as(ADMIN)
    data = c.get(f"{URL}?status=completed").get_json()["data"]
    assert data and all(r["status"] == "completed" for r in data)
    detail = c.get(f"{URL}/{data[0]['id']}").get_json()["data"]
    assert all(h["by_name"] and h["role"] for h in detail["history"])
    assert c.get(f"{URL}?status=done").status_code == 400


# ---------- syarat batch (keputusan 13 Nov 2026) ----------

def test_normal_batch_can_only_be_requested_as_a_deliberate_damage_report(login_as, db):
    c = login_as(STAFF)
    normal = batch_of(db, "P004")  # Mie instan, sisa 180 hari, layak
    no_basis = _submit(c, normal)  # tanpa memilih "barang rusak": tidak boleh otomatis
    assert no_basis.status_code == 400 and "Pilih dulu" in no_basis.get_json()["error"]["message"]
    assert _submit(c, normal, basis="near_expiry").status_code == 400  # barang layak yang masih lama tidak boleh diretur
    assert _submit(c, normal, basis="damaged", quantity=2, reason="Kemasan basah").status_code == 201


def test_expired_batch_must_be_handled_whole(login_as, db):
    c = login_as(STAFF)
    expired = batch_of(db, "P006")          # Yogurt Expired, stok 5 (pengajuan returnya ditolak di seed)
    assert _submit(c, expired, request_type="return", quantity=4).status_code == 400
    assert _submit(c, expired, request_type="disposal", quantity=expired["current_quantity"]).status_code == 201


def test_all_damaged_units_must_be_requested_together(login_as, db):
    c = login_as(STAFF)
    batch = batch_of(db, "P004")             # Normal, stok 100
    c.post("/api/v1/inspections", json={"batch_id": str(batch["_id"]), "physical_quantity": batch["current_quantity"],
                                        "product_condition": "rusak", "packaging_condition": "baik",
                                        "damaged_quantity": 4, "notes": "4 bungkus basah", "client_request_id": rid()})
    assert _submit(c, batch, request_type="disposal", quantity=3).status_code == 400
    created = _submit(c, batch, request_type="disposal", quantity=4)
    assert created.status_code == 201 and created.get_json()["data"]["basis"] == "damaged"


def test_batch_with_damage_and_near_expiry_must_choose_basis(login_as, db):
    c = login_as(STAFF)
    roti = batch_of(db, "P005")              # Critical, stok 12, 3 rusak (sudah diajukan di seed), 9 masih bagus
    assert _submit(c, roti, request_type="return", quantity=9).status_code == 400            # basis belum dipilih
    assert _submit(c, roti, request_type="return", quantity=3, basis="damaged").status_code == 409  # sudah ada
    assert _submit(c, roti, request_type="return", quantity=10, basis="near_expiry").status_code == 400
    assert _submit(c, roti, request_type="disposal", quantity=9, basis="near_expiry").status_code == 400
    assert _submit(c, roti, request_type="return", quantity=9, basis="near_expiry").status_code == 201


def test_completing_damaged_request_clears_the_damage(login_as, db):
    roti = batch_of(db, "P005")
    staff = login_as(STAFF)
    before = staff.get(f"/api/v1/batches/{roti['_id']}").get_json()["data"]
    assert before["damaged_quantity"] == 3 and before["fitness"] == "partial" and before["sellable_quantity"] == 9
    req = db.handling_requests.find_one({"batch_id": roti["_id"], "status": "approved"})
    done = staff.post(f"{URL}/{req['_id']}/complete", json={"handled_quantity": 3, "note": NOTE})
    assert done.status_code == 200
    after = staff.get(f"/api/v1/batches/{roti['_id']}").get_json()["data"]
    assert after["current_quantity"] == 9 and after["damaged_quantity"] == 0 and after["fitness"] == "fit"
    assert after["sellable_quantity"] == 9 and reconcile(db, roti["_id"]) == 9


def test_fit_critical_batch_may_be_partial(login_as, db):
    assert _submit(login_as(STAFF), batch_of(db, "P009"), request_type="return", quantity=3).status_code == 201


def test_request_options_are_sent_to_the_screen(login_as, db):
    c = login_as(STAFF)
    options = {b["sku"]: [o["basis"] for o in b["request_options"]]
               for b in c.get("/api/v1/batches?limit=100").get_json()["data"]
               if b["sku"] in ("P004", "P009", "P013", "P005")}
    assert options == {"P004": ["damaged"], "P009": ["damaged", "near_expiry"], "P013": ["expired"],
                       "P005": ["damaged", "near_expiry"]}  # "damaged" pada P004/P009 = laporan rusak langsung


# ---------- urutan ritel: jual -> retur -> musnahkan (keputusan 14 Nov 2026) ----------

def test_fit_batch_cannot_be_disposed_only_returned(login_as, db):
    c = login_as(STAFF)
    response = _submit(c, batch_of(db, "P009"), request_type="disposal", quantity=3)  # Kopi: Critical, layak
    assert response.status_code == 400 and "Pemusnahan hanya untuk barang kedaluwarsa atau rusak" in response.get_json()["error"]["message"]
    assert _submit(c, batch_of(db, "P009"), request_type="return", quantity=3).status_code == 201


def test_completion_always_needs_evidence_note(login_as, db):
    doc = _new(login_as, db, request_type="return", quantity=2)
    login_as(SUPERVISOR).post(f"{URL}/{doc['id']}/approve", json={})
    c = login_as(STAFF)
    no_note = c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 2})
    assert no_note.status_code == 400 and "pemasok" in no_note.get_json()["error"]["message"]
    assert c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 2, "note": "ok"}).status_code == 400
    assert c.post(f"{URL}/{doc['id']}/complete", json={"handled_quantity": 2, "note": NOTE}).status_code == 200
    assert db.handling_requests.find_one({"request_number": doc["request_number"]})["completion_note"] == NOTE


def test_seed_disposal_has_method_and_witness(db):
    done = db.handling_requests.find_one({"status": "completed", "request_type": "disposal"})
    assert "disaksikan" in done["completion_note"]



def test_expired_request_blocked_while_other_request_is_open(login_as, db):
    from datetime import timedelta

    from app.common.dates import today_jakarta
    c = login_as(STAFF)
    roti = batch_of(db, "P005")    # masih ada pengajuan barang rusak (Disetujui) dari seed
    db.batches.update_one({"_id": roti["_id"]}, {"$set": {"expiry_date": (today_jakarta() - timedelta(days=1)).isoformat()}})
    blocked = _submit(c, roti, request_type="disposal", quantity=12)
    assert blocked.status_code == 409 and "belum selesai" in blocked.get_json()["error"]["message"]
    req = db.handling_requests.find_one({"batch_id": roti["_id"], "status": "approved"})
    login_as(SUPERVISOR).post(f"{URL}/{req['_id']}/cancel", json={"note": "Ditangani bersama sebagai barang Expired"})
    assert _submit(c, roti, request_type="disposal", quantity=12).status_code == 201


def test_batch_shows_which_options_are_blocked_by_open_requests(login_as, db):
    """Tampilan harus tahu sebelum form diisi: pilihan yang terhalang pengajuan terbuka diberi tanda blocked_by."""
    from datetime import timedelta

    from app.common.dates import today_jakarta
    c = login_as(STAFF)
    roti = batch_of(db, "P005")    # pengajuan barang rusak (Disetujui) dari seed
    data = c.get(f"/api/v1/batches/{roti['_id']}").get_json()["data"]
    assert [r["status"] for r in data["open_requests"]] == ["approved"]
    options = {o["basis"]: o for o in data["request_options"]}
    assert options["damaged"]["blocked_by"]["request_number"] == data["open_requests"][0]["request_number"]
    assert "blocked_by" not in options["near_expiry"]           # barang bagus masih boleh diretur

    db.batches.update_one({"_id": roti["_id"]}, {"$set": {"expiry_date": (today_jakarta() - timedelta(days=1)).isoformat()}})
    data = c.get(f"/api/v1/batches/{roti['_id']}").get_json()["data"]
    assert [o["basis"] for o in data["request_options"]] == ["expired"]
    assert data["request_options"][0]["blocked_by"]["status"] == "approved"   # Expired menunggu pengajuan lama selesai

    jeruk = batch_of(db, "P009")    # belum ada pengajuan
    data = c.get(f"/api/v1/batches/{jeruk['_id']}").get_json()["data"]
    assert data["open_requests"] == [] and all("blocked_by" not in o for o in data["request_options"])
