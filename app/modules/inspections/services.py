"""Pemeriksaan fisik (cek fisik), penyesuaian stok, dan koreksi tanggal kedaluwarsa (SD 5.5 A dan 5.3 C).

Pemeriksaan:
- Dicatat Staff atau Supervisor. Setiap pemeriksaan adalah catatan BARU; riwayat tidak pernah ditimpa.
- Pemeriksaan TIDAK mengubah stok. Stok sistem saat itu, selisih, dan jumlah rusak disimpan sebagai snapshot.
- Jumlah dihitung = SEMUA barang batch itu, termasuk yang rusak. Bila ada yang rusak, jumlah rusaknya dicatat;
  hanya barang rusak itu yang wajib diretur/dimusnahkan, sisanya tetap boleh dijual (standar ritel: barang
  rusak dipisahkan per buah).
- Tanggal kedaluwarsa di kemasan dicocokkan. Bila berbeda, tanggal di kemasan menjadi USULAN koreksi yang harus
  disetujui Supervisor (bukan pemeriksanya sendiri) sebelum tanggal batch berubah.
- Catatan wajib bila ada selisih, barang rusak, atau tanggal di kemasan berbeda.

Penyesuaian stok (hanya Staff, tanpa persetujuan Supervisor, tetapi selalu tampil di pemberitahuan Supervisor
dan Admin):
- Wajib berasal dari pemeriksaan yang memiliki selisih; arah dan jumlah otomatis dari selisih.
- Satu pemeriksaan hanya menghasilkan satu penyesuaian (indeks unik source.inspection_id).
- Ditolak bila stok batch sudah berubah sejak pemeriksaan (selisihnya sudah tidak berlaku).
"""
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from ...common.audit import log_action
from ...common.constants import ROLE_SUPERVISOR
from ...common.dates import parse_iso_date, today_jakarta, utc_bounds
from ...common.errors import Conflict, Forbidden, NotFound, ValidationFailed
from ...common.http import clean_text, parse_client_request_id, parse_enum, parse_object_id, parse_quantity
from ...common.transactions import transaction
from ..batches import services as batch_services
from ..movements.ledger import record_movement

CONDITIONS = ("baik", "rusak")
CONDITION_LABELS = {"baik": "Baik", "rusak": "Rusak"}
EXPIRY_LABEL_CHECKS = ("match", "different")
CORRECTION_STATUS_LABELS = {"pending": "Menunggu", "approved": "Disetujui", "rejected": "Ditolak"}


def validate_inspection(data, batch):
    system_quantity = batch["current_quantity"]
    physical = parse_quantity(data.get("physical_quantity"), "physical_quantity", "Jumlah fisik",
                              max_value=batch_services.MAX_QUANTITY, minimum=0)
    product_condition = parse_enum(data.get("product_condition"), CONDITIONS, "product_condition", "Kondisi produk")
    packaging_condition = parse_enum(data.get("packaging_condition"), CONDITIONS, "packaging_condition",
                                     "Kondisi kemasan")
    has_damage = "rusak" in (product_condition, packaging_condition)
    if has_damage:
        if physical == 0:
            raise ValidationFailed("Jumlah dihitung 0, jadi tidak ada barang yang bisa dinyatakan rusak.",
                                   {"damaged_quantity": "Tidak ada barang."})
        damaged = parse_quantity(data.get("damaged_quantity"), "damaged_quantity", "Jumlah yang rusak",
                                 max_value=physical)
    else:
        if data.get("damaged_quantity") not in (None, "", 0, "0"):
            raise ValidationFailed("Kondisi produk dan kemasan baik, jadi jumlah yang rusak harus 0.",
                                   {"damaged_quantity": "Harus 0 bila kondisinya baik."})
        damaged = 0

    expiry_check = parse_enum(data.get("expiry_label") or "match", EXPIRY_LABEL_CHECKS, "expiry_label",
                              "Tanggal di kemasan")
    label_date = None
    if expiry_check == "different":
        label_date = parse_iso_date(data.get("label_expiry_date"), "label_expiry_date",
                                    "Tanggal kedaluwarsa di kemasan").isoformat()
        if label_date == batch["expiry_date"]:
            raise ValidationFailed("Tanggal di kemasan sama dengan yang tercatat. Pilih 'Sesuai'.",
                                   {"label_expiry_date": "Sama dengan yang tercatat."})

    unusual = physical != system_quantity or has_damage or expiry_check == "different"
    notes = clean_text(data, "notes", "Catatan", max_len=500, required=unusual)
    return {"physical_quantity": physical, "product_condition": product_condition,
            "packaging_condition": packaging_condition, "damaged_quantity": damaged,
            "expiry_label": expiry_check, "label_expiry_date": label_date, "notes": notes}


def build_inspection(batch, actor, fields, now):
    system_quantity = batch["current_quantity"]
    damaged = fields.get("damaged_quantity", 0)
    doc = {
        "batch_id": batch["_id"],
        "product_id": batch["product_id"],
        "system_quantity": system_quantity,
        "physical_quantity": fields["physical_quantity"],
        "difference": fields["physical_quantity"] - system_quantity,
        "product_condition": fields["product_condition"],
        "packaging_condition": fields["packaging_condition"],
        "damaged_quantity": damaged,
        "is_fit": damaged == 0,
        "expiry_label": fields.get("expiry_label", "match"),
        "expiry_correction": None,
        "notes": fields["notes"],
        "inspected_by": actor["_id"] if actor else None,
        "inspected_at": now,
    }
    if fields.get("label_expiry_date"):
        doc["expiry_correction"] = {"old_date": batch["expiry_date"], "proposed_date": fields["label_expiry_date"],
                                    "status": "pending", "decided_by": None, "decided_at": None, "note": ""}
    return doc


def create_inspection(db, actor, data):
    client_request_id = parse_client_request_id(data)
    if db.inspections.find_one({"client_request_id": client_request_id}, {"_id": 1}):
        raise Conflict("Hasil cek ini sudah tersimpan (tombol tertekan dua kali). Tidak ada data ganda.")
    batch = batch_services.get_batch(db, parse_object_id(data.get("batch_id"), "batch_id"))
    fields = validate_inspection(data, batch)
    if fields["label_expiry_date"] and db.inspections.find_one(
            {"batch_id": batch["_id"], "expiry_correction.status": "pending"}, {"_id": 1}):
        raise Conflict("Kiriman ini masih punya usulan koreksi tanggal yang menunggu keputusan Supervisor.",
                       {"label_expiry_date": "Masih ada usulan yang menunggu."})
    inspection = build_inspection(batch, actor, fields, datetime.now(timezone.utc))
    inspection["client_request_id"] = client_request_id
    try:
        inspection["_id"] = db.inspections.insert_one(inspection).inserted_id
    except DuplicateKeyError:
        raise Conflict("Hasil cek ini sudah tersimpan (tombol tertekan dua kali). Tidak ada data ganda.")
    log_action(db, actor, "inspection_recorded", "inspections", inspection["_id"],
               details={"batch_number": batch["batch_number"], "difference": inspection["difference"],
                        "damaged_quantity": inspection["damaged_quantity"],
                        "proposed_expiry_date": fields["label_expiry_date"]})
    return get_inspection(db, inspection["_id"])


def _reset_correction(db, inspection_id):
    db.inspections.update_one({"_id": inspection_id},
                              {"$set": {"expiry_correction.status": "pending", "expiry_correction.decided_by": None,
                                        "expiry_correction.decided_at": None, "expiry_correction.note": ""}})


def decide_expiry_correction(db, actor, inspection_id, decision, data):
    """Supervisor menyetujui/menolak usulan koreksi tanggal kedaluwarsa dari cek fisik.
    Disetujui -> tanggal kedaluwarsa batch diganti; tanggal lama disimpan di riwayat batch (expiry_history)."""
    inspection = db.inspections.find_one({"_id": inspection_id})
    if not inspection:
        raise NotFound("Data cek fisik tidak ditemukan.")
    correction = inspection.get("expiry_correction") or {}
    if correction.get("status") != "pending":
        raise Conflict("Usulan koreksi tanggal ini sudah diputuskan atau tidak ada.")
    if actor["role"] != ROLE_SUPERVISOR:
        raise Forbidden("Hanya Supervisor yang dapat memutuskan koreksi tanggal.")
    if inspection.get("inspected_by") == actor["_id"]:
        raise Forbidden("Anda tidak dapat memutuskan usulan dari cek fisik Anda sendiri.")
    note = clean_text(data, "note", "Catatan", max_len=500, required=(decision == "reject"))
    new_status = "approved" if decision == "approve" else "rejected"
    now = datetime.now(timezone.utc)
    batch = db.batches.find_one({"_id": inspection["batch_id"]})
    pending = {"_id": inspection_id, "expiry_correction.status": "pending"}
    decided = {"expiry_correction.status": new_status, "expiry_correction.decided_by": actor["_id"],
               "expiry_correction.decided_at": now, "expiry_correction.note": note}

    with transaction(db) as session:
        if db.inspections.update_one(pending, {"$set": decided}, session=session).modified_count == 0:
            raise Conflict("Usulan koreksi tanggal ini sudah diputuskan sebelumnya.")
        if new_status == "approved":
            history = {"old_date": correction["old_date"], "new_date": correction["proposed_date"],
                       "inspection_id": inspection_id, "proposed_by": inspection.get("inspected_by"),
                       "approved_by": actor["_id"], "approved_at": now, "note": note}
            changed = db.batches.update_one(
                {"_id": batch["_id"], "expiry_date": correction["old_date"]},
                {"$set": {"expiry_date": correction["proposed_date"], "updated_at": now},
                 "$push": {"expiry_history": history}}, session=session)
            if changed.modified_count == 0:
                if session is None:  # tanpa transaksi: kembalikan status usulan secara manual
                    _reset_correction(db, inspection_id)
                raise Conflict("Tanggal kedaluwarsa kiriman ini sudah berubah sejak cek fisik. Lakukan cek ulang.")
    log_action(db, actor, "expiry_corrected" if new_status == "approved" else "expiry_correction_rejected",
               "batches", batch["_id"],
               details={"batch_number": batch["batch_number"], "old_expiry_date": correction["old_date"],
                        "new_expiry_date": correction["proposed_date"], "note": note})
    return get_inspection(db, inspection_id)


def adjust_from_inspection(db, actor, inspection_id):
    """Sesuaikan stok sistem agar sama dengan hasil hitung fisik pada pemeriksaan ini."""
    inspection = db.inspections.find_one({"_id": inspection_id})
    if not inspection:
        raise NotFound("Pemeriksaan tidak ditemukan.")
    difference = inspection["difference"]
    if difference == 0:
        raise ValidationFailed("Pemeriksaan ini tidak memiliki selisih, jadi tidak perlu menyamakan stok.")
    if db.stock_movements.find_one({"source.inspection_id": inspection_id}, {"_id": 1}):
        raise Conflict("Pemeriksaan ini sudah dipakai untuk menyamakan stok.")
    if db.stock_movements.find_one({"batch_id": inspection["batch_id"],
                                    "created_at": {"$gt": inspection["inspected_at"]}}, {"_id": 1}):
        raise Conflict("Stok berubah sejak pemeriksaan; lakukan pemeriksaan ulang.")

    batch = db.batches.find_one({"_id": inspection["batch_id"]})
    movement_type = "adjustment_in" if difference > 0 else "adjustment_out"
    when = inspection["inspected_at"]
    reason = f"Stok disamakan dari cek fisik: tercatat {inspection['system_quantity']}, hitungan {inspection['physical_quantity']}"
    with transaction(db) as session:
        movement = record_movement(
            db, batch, actor, movement_type, abs(difference), movement_date=today_jakarta().isoformat(),
            reason=reason, notes=inspection.get("notes", ""),
            source={"type": "inspection", "inspection_id": inspection_id},
            expected_quantity=inspection["system_quantity"], session=session)
    log_action(db, actor, "stock_adjusted", "stock_movements", movement["_id"],
               details={"batch_number": batch["batch_number"], "movement_type": movement_type,
                        "quantity": abs(difference), "inspection_id": str(inspection_id),
                        "inspected_at": when.isoformat() if hasattr(when, "isoformat") else str(when)})
    return movement


def enrich(db, items):
    batch_ids = list({i["batch_id"] for i in items})
    batches = {b["_id"]: b for b in db.batches.find({"_id": {"$in": batch_ids}},
                                                    {"batch_number": 1, "current_quantity": 1})}
    products = {p["_id"]: p for p in db.master_product.find({"_id": {"$in": [i["product_id"] for i in items]}},
                                                      {"sku": 1, "name": 1, "unit": 1})}
    user_ids = [i["inspected_by"] for i in items if i.get("inspected_by")]
    user_ids += [(i.get("expiry_correction") or {}).get("decided_by") for i in items]
    users = {u["_id"]: u for u in db.master_karyawan.find({"_id": {"$in": [u for u in user_ids if u]}}, {"name": 1})}
    adjustments = {m["source"]["inspection_id"]: m for m in db.stock_movements.find(
        {"source.inspection_id": {"$in": [i["_id"] for i in items]}}, {"source": 1, "movement_type": 1, "quantity": 1})}
    # pergerakan terakhir per batch, untuk mengetahui apakah selisih pemeriksaan masih berlaku
    last_move = {}
    for m in db.stock_movements.find({"batch_id": {"$in": batch_ids}}, {"batch_id": 1, "created_at": 1}).sort("created_at", -1):
        last_move.setdefault(m["batch_id"], m["created_at"])
    for item in items:
        batch = batches.get(item["batch_id"], {})
        product = products.get(item["product_id"], {})
        item["batch_number"] = batch.get("batch_number")
        item["sku"], item["product_name"], item["unit"] = product.get("sku"), product.get("name"), product.get("unit")
        item["inspected_by_name"] = users.get(item.get("inspected_by"), {}).get("name") or "-"
        item.setdefault("damaged_quantity", 0 if item.get("is_fit") else item.get("physical_quantity", 0))
        correction = item.get("expiry_correction")
        if correction:
            correction["decided_by_name"] = users.get(correction.get("decided_by"), {}).get("name")
        adjustment = adjustments.get(item["_id"])
        item["adjusted"] = adjustment is not None
        item["adjustment_movement_id"] = adjustment["_id"] if adjustment else None
        moved_after = last_move.get(item["batch_id"]) is not None and last_move[item["batch_id"]] > item["inspected_at"]
        item["adjustment_status"] = (
            "none" if item["difference"] == 0 else
            "adjusted" if adjustment else
            "stale" if moved_after or batch.get("current_quantity") != item["system_quantity"] else
            "available")
    return items


def list_inspections(db, filters, skip, limit, sort):
    query = build_query(filters)
    total = db.inspections.count_documents(query)
    items = list(db.inspections.find(query).sort(sort).skip(skip).limit(limit))
    return enrich(db, items), total


def build_query(filters):
    query = {}
    if filters.get("batch_id"):
        query["batch_id"] = parse_object_id(filters["batch_id"], "batch_id")
    if filters.get("product_id"):
        query["product_id"] = parse_object_id(filters["product_id"], "product_id")
    if filters.get("fitness"):
        query["is_fit"] = parse_enum(filters["fitness"], ("fit", "unfit"), "fitness", "Kelayakan") == "fit"
    if filters.get("has_difference") == "true":
        query["difference"] = {"$ne": 0}
    if filters.get("correction"):
        query["expiry_correction.status"] = parse_enum(filters["correction"], tuple(CORRECTION_STATUS_LABELS),
                                                       "correction", "Koreksi tanggal")
    bounds = utc_bounds(filters.get("date_from"), filters.get("date_to"))
    if bounds:
        query["inspected_at"] = bounds
    return query


def get_inspection(db, inspection_id):
    item = db.inspections.find_one({"_id": inspection_id})
    if not item:
        raise NotFound("Data tidak ditemukan.")
    return enrich(db, [item])[0]
