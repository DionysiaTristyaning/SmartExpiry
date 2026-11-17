"""Batch dan stok masuk (SD 5.3 A).

Aturan:
- Setiap penerimaan barang SELALU menjadi batch baru dengan nomor internal dari sistem (BT-YYMMDD-NNN).
- Batch dibuat bersama satu pergerakan `stock_in` dalam satu transaksi.
- Data batch (produk, tanggal masuk, jumlah awal) tidak dapat diubah setelah disimpan, karena itu ada langkah
  pratinjau/konfirmasi sebelum menyimpan. Tanggal kedaluwarsa hanya dapat dikoreksi lewat usulan dari cek fisik
  yang disetujui Supervisor (lihat inspections.services).
- Tanggal masuk <= hari ini; tanggal kedaluwarsa > tanggal masuk dan > hari ini (barang kedaluwarsa,
  termasuk yang kedaluwarsa hari ini, tidak dicatat sebagai penerimaan baru).
- Jumlah datang boleh diisi dalam satuan besar (misalnya 3 karton + 5 pcs) bila produknya punya satuan besar;
  sistem mengubahnya ke satuan terkecil. Stok selalu dalam satuan terkecil.
- Barang yang rusak saat datang DITOLAK di penerimaan (dikembalikan ke pemasok saat itu juga): tidak masuk stok,
  tetapi jumlah dan alasannya tercatat di batch dan audit log. Bila semua ditolak, tidak ada batch yang dibuat.
"""
import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from ...common.audit import log_action
from ...common.dates import parse_iso_date, today_jakarta
from ...common.errors import Conflict, NotFound, ValidationFailed
from ...common.http import clean_text, parse_client_request_id, parse_enum, parse_object_id, parse_quantity
from ...common.numbering import MAX_ATTEMPTS, next_number, prefix_for
from ...common.transactions import transaction
from ..expiry import services as expiry
from ..movements.ledger import ensure_new_client_request, record_movement
from ..products import services as product_services

MAX_QUANTITY = 100_000


def validate_stock_in_fields(data, today):
    """Periksa jumlah dan tanggal penerimaan (dipakai juga impor CSV). Mengembalikan dict field batch."""
    quantity = parse_quantity(data.get("quantity"), "quantity", "Jumlah", max_value=MAX_QUANTITY)
    return {"quantity": quantity, **validate_dates(data, today)}


def validate_dates(data, today):
    received = parse_iso_date(data.get("received_date"), "received_date", "Tanggal barang datang")
    expiry_date = parse_iso_date(data.get("expiry_date"), "expiry_date", "Tanggal kedaluwarsa")
    if received > today:
        raise ValidationFailed("Tanggal barang datang tidak boleh di masa depan.", {"received_date": "Melewati hari ini."})
    if expiry_date <= received:
        raise ValidationFailed("Tanggal kedaluwarsa harus setelah tanggal barang datang.",
                               {"expiry_date": "Tidak setelah tanggal barang datang."})
    if expiry_date <= today:
        raise ValidationFailed("Barang yang sudah kedaluwarsa (termasuk yang kedaluwarsa hari ini) tidak dapat "
                               "dicatat sebagai penerimaan baru.", {"expiry_date": "Sudah kedaluwarsa."})
    return {"received_date": received.isoformat(), "expiry_date": expiry_date.isoformat()}


def _active_product(db, product_id):
    product = db.master_product.find_one({"_id": product_id})
    if not product or not product.get("is_active"):
        raise ValidationFailed("Produk tidak ditemukan atau tidak aktif.", {"product_id": "Produk tidak valid."})
    return product


def _empty(value):
    return value in (None, "", 0, "0")


def parse_receipt(product, data):
    """Jumlah datang (satuan besar + satuan kecil), jumlah ditolak, dan alasannya.
    Mengembalikan dict: received_quantity, rejected_quantity, reject_reason, quantity (= diterima), pack."""
    pack_size = product.get("pack_size") or 0
    packs = 0
    if not _empty(data.get("pack_quantity")):
        if not pack_size:
            raise ValidationFailed("Produk ini belum punya satuan besar (misalnya karton). Isi jumlahnya dalam "
                                   f"{product.get('unit') or 'satuan biasa'}.", {"pack_quantity": "Tidak tersedia."})
        packs = parse_quantity(data.get("pack_quantity"), "pack_quantity", f"Jumlah {product['pack_unit']}",
                               max_value=MAX_QUANTITY)
    loose = data.get("quantity")
    if packs and loose in (None, ""):
        loose = 0
    loose = parse_quantity(loose, "quantity", "Jumlah yang datang", max_value=MAX_QUANTITY, minimum=0 if packs else 1)
    total = packs * pack_size + loose
    if total > MAX_QUANTITY:
        raise ValidationFailed(f"Jumlah yang datang terlalu besar (paling banyak {MAX_QUANTITY}).",
                               {"quantity": f"Maksimal {MAX_QUANTITY}."})
    rejected = 0
    if not _empty(data.get("rejected_quantity")):
        rejected = parse_quantity(data.get("rejected_quantity"), "rejected_quantity", "Jumlah ditolak",
                                  max_value=total, minimum=0)
    reason = clean_text(data, "reject_reason", "Alasan ditolak", max_len=200, required=rejected > 0)
    return {"received_quantity": total, "rejected_quantity": rejected, "reject_reason": reason if rejected else "",
            "quantity": total - rejected,
            "pack": {"unit": product["pack_unit"], "size": pack_size, "count": packs, "loose": loose} if packs else None}


def _parse_stock_in(db, data):
    product = _active_product(db, parse_object_id(data.get("product_id"), "product_id"))
    fields = parse_receipt(product, data)
    fields.update(validate_dates(data, today_jakarta()))
    fields["notes"] = clean_text(data, "notes", "Catatan", max_len=500, required=False)
    return product, fields


def preview_stock_in(db, data):
    """Ringkasan untuk layar konfirmasi. Tidak menyimpan apa pun."""
    product, fields = _parse_stock_in(db, data)
    return {"sku": product["sku"], "product_name": product["name"], "unit": product["unit"], **fields,
            **expiry.compute(fields["expiry_date"], today_jakarta())}


def create_batch_with_stock_in(db, actor, product, fields, source, client_request_id=None, now=None):
    """Buat batch baru + stock_in dalam satu transaksi. Nomor batch diulang bila bentrok."""
    now = now or datetime.now(timezone.utc)
    prefix = prefix_for("BT", datetime.fromisoformat(fields["received_date"]))
    for _ in range(MAX_ATTEMPTS):
        try:
            with transaction(db) as session:
                ensure_new_client_request(db, client_request_id, session)
                batch = {
                    "_id": ObjectId(),
                    "batch_number": next_number(db, "batches", "batch_number", prefix, session=session),
                    "product_id": product["_id"],
                    "received_date": fields["received_date"],
                    "expiry_date": fields["expiry_date"],
                    "initial_quantity": fields["quantity"],
                    "received_quantity": fields.get("received_quantity", fields["quantity"]),
                    "rejected_quantity": fields.get("rejected_quantity", 0),
                    "reject_reason": fields.get("reject_reason", ""),
                    "pack": fields.get("pack"),
                    "current_quantity": 0,  # langsung diisi oleh stock_in di bawah
                    "created_by": actor["_id"] if actor else None,
                    "created_at": now,
                    "updated_at": now,
                }
                db.batches.insert_one(batch, session=session)
                try:
                    movement = record_movement(
                        db, batch, actor, "stock_in", fields["quantity"], movement_date=fields["received_date"],
                        notes=fields.get("notes", ""), source=source, client_request_id=client_request_id,
                        session=session, now=now)
                except Exception:
                    if session is None:
                        db.batches.delete_one({"_id": batch["_id"]})
                    raise
            batch["current_quantity"] = fields["quantity"]
            return batch, movement
        except DuplicateKeyError:
            continue  # nomor batch bentrok dengan penyimpanan lain; coba nomor berikutnya
    raise ValidationFailed("Gagal membuat nomor kiriman. Coba simpan lagi.")


def create_stock_in(db, actor, data):
    client_request_id = parse_client_request_id(data)
    product, fields = _parse_stock_in(db, data)
    if fields["quantity"] == 0:
        return _reject_all(db, actor, product, fields, client_request_id)
    batch, movement = create_batch_with_stock_in(db, actor, product, fields, {"type": "manual"}, client_request_id)
    log_action(db, actor, "stock_in_recorded", "batches", batch["_id"],
               details={"batch_number": batch["batch_number"], "sku": product["sku"], "quantity": fields["quantity"],
                        "rejected_quantity": fields["rejected_quantity"], "reject_reason": fields["reject_reason"],
                        "expiry_date": fields["expiry_date"]})
    return get_batch(db, batch["_id"])


def _reject_all(db, actor, product, fields, client_request_id):
    """Semua barang ditolak saat datang: tidak ada batch dan stok tidak berubah, tetapi kejadiannya dicatat."""
    if db.audit_logs.find_one({"action": "receipt_rejected", "details.client_request_id": client_request_id}, {"_id": 1}):
        raise Conflict("Data ini sudah tersimpan (tombol tertekan dua kali). Tidak ada data ganda.")
    details = {"sku": product["sku"], "rejected_quantity": fields["rejected_quantity"],
               "reject_reason": fields["reject_reason"], "expiry_date": fields["expiry_date"],
               "client_request_id": client_request_id}
    log_action(db, actor, "receipt_rejected", "master_product", product["_id"], details=details)
    return {"rejected_all": True, "sku": product["sku"], "product_name": product["name"], "unit": product.get("unit"),
            "rejected_quantity": fields["rejected_quantity"], "reject_reason": fields["reject_reason"]}


# ---------- membaca ----------

def get_batch(db, batch_id):
    batch = db.batches.find_one({"_id": batch_id})
    if not batch:
        raise NotFound("Kiriman tidak ditemukan.")
    return enrich(db, [batch])[0]


def enrich(db, batches, today=None):
    """Tambahkan data produk, status kedaluwarsa, pemeriksaan terakhir, dan kelayakan (dihitung saat ini)."""
    today = today or today_jakarta()
    products = {p["_id"]: p for p in db.master_product.find({"_id": {"$in": list({b["product_id"] for b in batches})}})}
    latest = expiry.latest_inspections(db, [b["_id"] for b in batches])
    damaged_map = expiry.open_damaged(db, batches, latest)
    open_map = _open_requests(db, batches)
    for batch in batches:
        product = products.get(batch["product_id"], {})
        batch["sku"] = product.get("sku")
        batch["product_name"] = product.get("name")
        batch["unit"] = product.get("unit")
        batch["category"] = product.get("category")
        batch["price"] = product.get("price")
        batch.update(expiry.compute(batch["expiry_date"], today))
        inspection = latest.get(batch["_id"])
        batch["last_inspection"] = None if inspection is None else {
            "id": inspection["_id"], "inspected_at": inspection["inspected_at"],
            "product_condition": inspection["product_condition"],
            "packaging_condition": inspection["packaging_condition"], "is_fit": inspection["is_fit"],
            "damaged_quantity": expiry.inspection_damaged(inspection)}
        status, current = batch["expiry_status"], batch["current_quantity"]
        damaged = damaged_map.get(batch["_id"], 0)
        batch["damaged_quantity"] = damaged
        batch["sellable_quantity"] = expiry.sellable_quantity(status, current, damaged)
        batch["fitness"] = expiry.fitness(status, inspection, damaged, current)
        batch["sellable"] = batch["sellable_quantity"] > 0
        batch["request_options"] = expiry.request_options(status, current, damaged)
        batch["open_requests"] = open_map.get(batch["_id"], [])
        _mark_blocked(batch["request_options"], batch["open_requests"])
        batch.update(expiry.check_schedule(status, current, batch["received_date"], inspection, today))
    return batches


def _open_requests(db, batches):
    """{batch_id: [pengajuan Menunggu/Disetujui]} supaya tampilan tahu batch mana yang sudah diajukan."""
    result = {}
    cursor = db.handling_requests.find(
        {"batch_id": {"$in": [b["_id"] for b in batches]}, "status": {"$in": ["pending", "approved"]}},
        {"batch_id": 1, "request_number": 1, "status": 1, "basis": 1, "request_type": 1, "quantity": 1})
    for r in cursor.sort("submitted_at", 1):
        result.setdefault(r["batch_id"], []).append(
            {"id": str(r["_id"]), "request_number": r["request_number"], "status": r["status"],
             "basis": r.get("basis"), "request_type": r["request_type"], "quantity": r["quantity"]})
    return result


def _mark_blocked(options, open_requests):
    """Tandai pilihan yang belum bisa diajukan karena masih ada pengajuan terbuka (aturan sama dengan
    requests.submit): basis yang sama sudah diajukan, atau Barang Expired selama ada pengajuan lain di batch itu."""
    for option in options:
        blocker = next((r for r in open_requests
                        if option["basis"] == "expired" or r["basis"] == option["basis"]), None)
        if blocker:
            option["blocked_by"] = blocker


def list_batches(db, filters, skip, limit, sort):
    query = {}
    if filters.get("product_id"):
        query["product_id"] = parse_object_id(filters["product_id"], "product_id")
    status = filters.get("status")
    if status:
        parse_enum(status, expiry.STATUSES, "status", "Status kedaluwarsa")
        query["expiry_date"] = expiry.expiry_date_filter(status, today_jakarta())
    if filters.get("has_stock") == "true":
        query["current_quantity"] = {"$gt": 0}
    q = (filters.get("q") or "").strip()[:100]
    if q:
        product_ids = product_services.find_product_ids(db, q)
        query["$or"] = [{"batch_number": {"$regex": re.escape(q), "$options": "i"}},
                        {"product_id": {"$in": product_ids}}]
    total = db.batches.count_documents(query)
    items = list(db.batches.find(query).sort(sort + [("batch_number", 1)]).skip(skip).limit(limit))
    return enrich(db, items), total


def fefo_batches(db, product_id):
    """Batch yang boleh dijual untuk satu produk, urut FEFO (kedaluwarsa terdekat lebih dulu).
    Barang terjual dikurangi otomatis mulai dari batch pertama (lihat movements.services)."""
    today = today_jakarta()
    items = list(db.batches.find({"product_id": product_id, "current_quantity": {"$gt": 0},
                                  "expiry_date": expiry.not_expired_filter(today)})
                 .sort([("expiry_date", 1), ("batch_number", 1)]))
    return [b for b in enrich(db, items, today) if b["sellable"]]


def _user_names(db, ids):
    return {u["_id"]: u["name"] for u in db.master_karyawan.find({"_id": {"$in": [i for i in ids if i]}}, {"name": 1})}


def get_batch_detail(db, batch_id):
    batch = get_batch(db, batch_id)
    movements = list(db.stock_movements.find({"batch_id": batch_id}).sort("created_at", -1).limit(100))
    inspections = list(db.inspections.find({"batch_id": batch_id}).sort("inspected_at", -1).limit(50))
    requests = list(db.handling_requests.find({"batch_id": batch_id}).sort("submitted_at", -1).limit(50))
    names = _user_names(db, [m.get("created_by") for m in movements] + [i.get("inspected_by") for i in inspections]
                        + [r.get("submitted_by") for r in requests] + [batch.get("created_by")])
    for m in movements:
        m["created_by_name"] = names.get(m.get("created_by"), "-")
    for i in inspections:
        i["inspected_by_name"] = names.get(i.get("inspected_by"), "-")
    for r in requests:
        r["submitted_by_name"] = names.get(r.get("submitted_by"), "-")
    batch["created_by_name"] = names.get(batch.get("created_by"), "-")
    batch["movements"] = movements
    batch["inspections"] = inspections
    batch["requests"] = requests
    return batch


def sellable_by_product(db, product_ids=None):
    """{product_id: stok yang boleh dijual} dihitung dari semua batch ber-stok (dipakai stok minimum)."""
    query = {"current_quantity": {"$gt": 0}}
    if product_ids is not None:
        query["product_id"] = {"$in": list(product_ids)}
    totals = {}
    for batch in enrich(db, list(db.batches.find(query))):
        totals[batch["product_id"]] = totals.get(batch["product_id"], 0) + batch["sellable_quantity"]
    return totals
