"""Pengajuan penanganan barang kedaluwarsa / mendekati kedaluwarsa / rusak (SD 5.5 C).

Jenis: return (retur) dan disposal (pemusnahan). Keduanya wajib disetujui Supervisor.

Dasar pengajuan (basis), ditentukan dari kondisi batch (expiry.request_options):
    expired     -> batch Expired: SELURUH stok batch, retur atau pemusnahan
    damaged     -> barang rusak dari cek fisik: SEMUA barang rusak itu, retur atau pemusnahan
                   (sisa barang yang bagus tetap boleh dijual; standar ritel: rusak dipisah per buah)
    near_expiry -> batch Critical (1 bulan terakhir): sebagian/seluruh barang yang masih bagus, HANYA retur
Satu batch hanya boleh punya satu pengajuan terbuka untuk setiap dasar. Pengajuan Barang Expired (seluruh stok)
ditolak selama masih ada pengajuan lain yang terbuka untuk batch itu, supaya tidak ada barang yang diajukan dua kali.

Status:
    pending   --Supervisor setuju-->      approved
    pending   --Supervisor tolak-->       rejected   (alasan wajib)
    pending   --pengaju batalkan-->       cancelled
    approved  --Staff mana pun selesai--> completed  (sistem mencatat stock_out otomatis)
    approved  --Supervisor batalkan-->    cancelled  (alasan wajib)
Status akhir (rejected, completed, cancelled) tidak dapat diubah lagi.

Lima proses dibedakan: rekomendasi (dihitung, tidak disimpan) -> pengajuan (Staff) -> persetujuan (Supervisor)
-> pelaksanaan fisik (di luar aplikasi) -> pencatatan hasil (Staff; sistem mencatat pergerakan stok).
"""
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

from ...common.audit import log_action
from ...common.constants import ROLE_STAFF, ROLE_SUPERVISOR
from ...common.dates import JAKARTA, today_jakarta, utc_bounds
from ...common.errors import Conflict, Forbidden, NotFound, ValidationFailed
from ...common.http import clean_text, parse_client_request_id, parse_enum, parse_object_id, parse_quantity
from ...common.numbering import MAX_ATTEMPTS, next_number, prefix_for
from ...common.transactions import transaction
from ..batches import services as batch_services
from ..expiry.services import BASIS_LABELS, REQUEST_BASES
from ..movements.ledger import record_movement

REQUEST_TYPES = ("return", "disposal")
TYPE_LABELS = {"return": "Pengembalian", "disposal": "Pemusnahan"}
STATUSES = ("pending", "approved", "rejected", "completed", "cancelled")
STATUS_LABELS = {"pending": "Menunggu", "approved": "Disetujui", "rejected": "Ditolak",
                 "completed": "Selesai", "cancelled": "Dibatalkan"}
OPEN_STATUSES = ("pending", "approved")
ACTION_LABELS = {"submitted": "Diajukan", "approved": "Disetujui", "rejected": "Ditolak",
                 "cancelled": "Dibatalkan", "completed": "Diselesaikan"}


def _entry(action, actor, now, note=""):
    return {"action": action, "by": actor["_id"], "role": actor["role"], "at": now, "note": note}


def _get(db, request_id):
    doc = db.handling_requests.find_one({"_id": request_id})
    if not doc:
        raise NotFound("Pengajuan tidak ditemukan.")
    return doc


# ---------- syarat batch ----------

def choose_option(batch, data):
    """Pilih dasar pengajuan. Bila batch hanya punya satu pilihan, `basis` boleh dikosongkan."""
    options = {o["basis"]: o for o in batch["request_options"]}
    if not options:
        raise ValidationFailed("Tidak ada barang di kiriman ini yang bisa diajukan (stok habis atau seluruhnya sudah "
                               "ditahan oleh pengajuan lain).", {"batch_id": "Kiriman tidak memenuhi syarat."})
    basis = data.get("basis")
    if not basis:
        # Bila hanya ada satu pilihan biasa, itu yang dipakai. Laporan rusak langsung (`direct`) tidak pernah dipilih
        # otomatis: Staff harus memilihnya dengan sengaja.
        regular = [o for o in options.values() if not o.get("direct")]
        if len(regular) == 1:
            basis = regular[0]["basis"]
    if not basis:
        raise ValidationFailed("Pilih dulu barang mana yang diajukan (barang rusak atau barang yang masih bagus).",
                               {"basis": "Wajib dipilih."})
    parse_enum(basis, REQUEST_BASES, "basis", "Dasar pengajuan")
    if basis not in options:
        raise ValidationFailed(f"Kiriman ini tidak punya {BASIS_LABELS[basis].lower()} untuk diajukan.",
                               {"basis": "Tidak sesuai kondisi kiriman."})
    return options[basis]


# ---------- mengajukan (Staff) ----------

def submit(db, actor, data):
    client_request_id = parse_client_request_id(data)
    if db.handling_requests.find_one({"client_request_id": client_request_id}, {"_id": 1}):
        raise Conflict("Pengajuan ini sudah tersimpan (tombol tertekan dua kali). Tidak ada data ganda.")
    batch = batch_services.get_batch(db, parse_object_id(data.get("batch_id"), "batch_id"))
    request_type = parse_enum(data.get("request_type"), REQUEST_TYPES, "request_type", "Jenis pengajuan")
    if batch["current_quantity"] <= 0:
        raise ValidationFailed("Stok kiriman ini sudah 0, tidak ada yang perlu ditangani.")
    option = choose_option(batch, data)
    basis = option["basis"]
    if request_type not in option["types"]:
        # Urutan ritel: jual (FEFO) -> retur ke pemasok -> musnahkan (pilihan terakhir). Barang layak tidak dibuang.
        raise ValidationFailed("Pemusnahan hanya untuk barang kedaluwarsa atau rusak. Barang yang masih bagus dijual "
                               "lebih dulu atau dikembalikan ke pemasok.", {"request_type": "Hanya pengembalian untuk barang layak."})
    quantity = parse_quantity(data.get("quantity"), "quantity", "Jumlah", max_value=option["quantity"])
    if option["fixed"] and quantity != option["quantity"]:
        what = "Kiriman kedaluwarsa harus ditangani seluruhnya" if basis == "expired" \
            else "Semua barang rusak harus diajukan sekaligus"
        raise ValidationFailed(f"{what} ({option['quantity']} {batch.get('unit') or 'unit'}).",
                               {"quantity": f"Harus {option['quantity']}."})
    reason = clean_text(data, "reason", "Alasan", max_len=500)

    if basis == "expired" and db.handling_requests.find_one(
            {"batch_id": batch["_id"], "status": {"$in": list(OPEN_STATUSES)}}, {"_id": 1}):
        # Mencegah penumpukan: pengajuan lama (barang rusak / mendekati kedaluwarsa) masih mencakup sebagian stok
        raise Conflict("Kiriman ini masih punya pengajuan lain yang belum selesai. Selesaikan atau batalkan pengajuan "
                       "itu dulu, lalu ajukan sisa barang kedaluwarsa.", {"basis": "Masih ada pengajuan terbuka."})
    if db.handling_requests.find_one({"batch_id": batch["_id"], "basis": basis,
                                      "status": {"$in": list(OPEN_STATUSES)}}, {"_id": 1}):
        raise Conflict(f"Masih ada pengajuan untuk {BASIS_LABELS[basis].lower()} di kiriman ini yang belum selesai.",
                       {"basis": "Masih ada yang terbuka."})

    now = datetime.now(timezone.utc)
    prefix = prefix_for("PG", today_jakarta())
    for _ in range(MAX_ATTEMPTS):
        doc = {
            "request_number": next_number(db, "handling_requests", "request_number", prefix),
            "batch_id": batch["_id"],
            "product_id": batch["product_id"],
            "request_type": request_type,
            "basis": basis,
            # "direct" = Staff melaporkan barang rusak langsung di form Ajukan (tanpa Cek Fisik): jumlahnya DITAHAN
            # (tidak bisa dijual) selama pengajuan Menunggu/Disetujui. "inspection" = rusak yang dicatat lewat Cek Fisik.
            "damage_source": ("direct" if option.get("direct") else "inspection") if basis == "damaged" else None,
            "quantity": quantity,
            "reason": reason,
            "status": "pending",
            "submitted_by": actor["_id"], "submitted_at": now,
            "reviewed_by": None, "reviewed_at": None, "review_note": "",
            "completed_by": None, "completed_at": None, "handled_quantity": None, "completion_note": "",
            "cancelled_by": None, "cancelled_at": None, "cancel_note": "",
            "stock_movement_id": None,
            "history": [_entry("submitted", actor, now, reason)],
            "client_request_id": client_request_id,
        }
        try:
            doc["_id"] = db.handling_requests.insert_one(doc).inserted_id
            break
        except DuplicateKeyError:
            if db.handling_requests.find_one({"client_request_id": client_request_id}, {"_id": 1}):
                raise Conflict("Pengajuan ini sudah tersimpan (tombol tertekan dua kali). Tidak ada data ganda.")
            continue  # nomor pengajuan bentrok; coba nomor berikutnya
    else:
        raise ValidationFailed("Gagal membuat nomor pengajuan. Coba ajukan lagi.")
    log_action(db, actor, "request_submitted", "handling_requests", doc["_id"],
               details={"request_number": doc["request_number"], "type": request_type, "basis": basis,
                        "quantity": quantity, "batch_number": batch["batch_number"]})
    return doc


# ---------- meninjau (Supervisor) ----------

def review(db, actor, request_id, decision, data):
    doc = _get(db, request_id)
    if actor["role"] != ROLE_SUPERVISOR:
        raise Forbidden("Hanya Supervisor yang dapat menyetujui atau menolak pengajuan.")
    if doc["submitted_by"] == actor["_id"]:
        raise Forbidden("Anda tidak dapat memutuskan pengajuan Anda sendiri.")
    note = clean_text(data, "note", "Catatan", max_len=500, required=(decision == "reject"))
    new_status = "approved" if decision == "approve" else "rejected"
    now = datetime.now(timezone.utc)
    updated = db.handling_requests.find_one_and_update(
        {"_id": request_id, "status": "pending"},  # keputusan hanya bisa diambil sekali
        {"$set": {"status": new_status, "reviewed_by": actor["_id"], "reviewed_at": now, "review_note": note},
         "$push": {"history": _entry(new_status, actor, now, note)}})
    if updated is None:
        raise Conflict("Pengajuan ini sudah diputuskan atau ditutup sebelumnya.")
    log_action(db, actor, f"request_{new_status}", "handling_requests", request_id,
               details={"request_number": doc["request_number"], "note": note})
    return _get(db, request_id)


# ---------- membatalkan ----------

def cancel(db, actor, request_id, data):
    """Pengaju membatalkan saat Menunggu; Supervisor membatalkan saat Disetujui (alasan wajib)."""
    doc = _get(db, request_id)
    if doc["status"] == "pending":
        if actor["role"] != ROLE_STAFF or doc["submitted_by"] != actor["_id"]:
            raise Forbidden("Pengajuan yang masih menunggu hanya dapat dibatalkan oleh orang yang mengajukannya.")
        note = clean_text(data, "note", "Catatan", max_len=500, required=False)
    elif doc["status"] == "approved":
        if actor["role"] != ROLE_SUPERVISOR:
            raise Forbidden("Pengajuan yang sudah disetujui hanya dapat dibatalkan oleh Supervisor.")
        note = clean_text(data, "note", "Alasan pembatalan", max_len=500)
    else:
        raise Conflict("Pengajuan ini sudah ditutup dan tidak dapat dibatalkan.")
    now = datetime.now(timezone.utc)
    updated = db.handling_requests.find_one_and_update(
        {"_id": request_id, "status": doc["status"]},
        {"$set": {"status": "cancelled", "cancelled_by": actor["_id"], "cancelled_at": now, "cancel_note": note},
         "$push": {"history": _entry("cancelled", actor, now, note)}})
    if updated is None:
        raise Conflict("Status pengajuan ini baru saja berubah. Muat ulang halaman (tekan F5) untuk melihat yang terbaru.")
    log_action(db, actor, "request_cancelled", "handling_requests", request_id,
               details={"request_number": doc["request_number"], "note": note})
    return _get(db, request_id)


# ---------- menyelesaikan (Staff mana pun) ----------

def complete(db, actor, request_id, data):
    """Catat hasil tindakan fisik. Sistem otomatis mencatat stock_out dalam transaksi yang sama."""
    doc = _get(db, request_id)
    if doc["status"] != "approved":
        raise Conflict("Pengajuan hanya dapat diselesaikan setelah disetujui.")
    handled = parse_quantity(data.get("handled_quantity"), "handled_quantity", "Jumlah yang ditangani",
                             max_value=doc["quantity"])
    # Catatan selalu wajib sebagai bukti (setara berita acara sederhana):
    #   retur      -> nama pemasok dan nomor dokumen/surat jalan retur
    #   pemusnahan -> cara pemusnahan dan saksi
    # Bila jumlah yang ditangani lebih kecil dari yang disetujui, alasannya juga ditulis di sini.
    label = "Keterangan pengembalian (pemasok dan nomor dokumen)" if doc["request_type"] == "return" \
        else "Keterangan pemusnahan (cara dan saksi)"
    note = clean_text(data, "note", label, max_len=500)
    if len(note) < 10:
        raise ValidationFailed(f"{label} terlalu singkat. Tulis minimal 10 karakter.", {"note": "Minimal 10 karakter."})
    batch = db.batches.find_one({"_id": doc["batch_id"]})
    state = batch_services.get_batch(db, batch["_id"])
    # Pengajuan lama (sebelum ada `basis`): tebak dari kondisi batch saat ini
    basis = doc.get("basis") or ("expired" if state["expiry_status"] == "expired"
                                 else "damaged" if state["damaged_quantity"] else "near_expiry")
    # Retur barang yang masih bagus tidak boleh mengambil jatah barang rusak yang belum ditangani
    reserve = state["damaged_quantity"] if basis == "near_expiry" else 0
    now = datetime.now(timezone.utc)

    with transaction(db) as session:
        # status diubah lebih dulu secara bersyarat: klik ganda tidak bisa menyelesaikan dua kali
        locked = db.handling_requests.find_one_and_update(
            {"_id": request_id, "status": "approved"},
            {"$set": {"status": "completed", "completed_by": actor["_id"], "completed_at": now,
                      "handled_quantity": handled, "completion_note": note},
             "$push": {"history": _entry("completed", actor, now, note)}}, session=session)
        if locked is None:
            raise Conflict("Pengajuan ini sudah diselesaikan atau ditutup.")
        try:
            movement = record_movement(
                db, batch, actor, "stock_out", handled, movement_date=today_jakarta().isoformat(),
                reason=f"{TYPE_LABELS[doc['request_type']]} {doc['request_number']}", notes=note,
                source={"type": "handling_request", "handling_request_id": request_id, "basis": basis},
                reserve=reserve, session=session, now=now)
            db.handling_requests.update_one({"_id": request_id}, {"$set": {"stock_movement_id": movement["_id"]}},
                                            session=session)
        except Exception:
            if session is None:  # tanpa transaksi: kembalikan status secara manual
                db.handling_requests.update_one({"_id": request_id}, {
                    "$set": {"status": "approved", "completed_by": None, "completed_at": None,
                             "handled_quantity": None, "completion_note": ""},
                    "$pop": {"history": 1}})
            raise
    log_action(db, actor, "request_completed", "handling_requests", request_id,
               details={"request_number": doc["request_number"], "handled_quantity": handled,
                        "stock_movement_id": str(movement["_id"])})
    return _get(db, request_id)


# ---------- membaca ----------

def enrich(db, items):
    batches = {b["_id"]: b for b in db.batches.find({"_id": {"$in": [i["batch_id"] for i in items]}},
                                                    {"batch_number": 1, "expiry_date": 1, "current_quantity": 1})}
    products = {p["_id"]: p for p in db.master_product.find({"_id": {"$in": [i["product_id"] for i in items]}},
                                                      {"sku": 1, "name": 1, "unit": 1})}
    user_ids = set()
    for item in items:
        user_ids.update(u for u in (item.get("submitted_by"), item.get("reviewed_by"), item.get("completed_by"),
                                    item.get("cancelled_by")) if u)
        user_ids.update(h["by"] for h in item.get("history", []) if h.get("by"))
    names = {u["_id"]: u["name"] for u in db.master_karyawan.find({"_id": {"$in": list(user_ids)}}, {"name": 1})}
    for item in items:
        batch = batches.get(item["batch_id"], {})
        product = products.get(item["product_id"], {})
        item["batch_number"] = batch.get("batch_number")
        item["expiry_date"] = batch.get("expiry_date")
        item["batch_quantity"] = batch.get("current_quantity")
        item["sku"], item["product_name"], item["unit"] = product.get("sku"), product.get("name"), product.get("unit")
        item["basis_label"] = BASIS_LABELS.get(item.get("basis"), "-")
        for key in ("submitted_by", "reviewed_by", "completed_by", "cancelled_by"):
            item[key + "_name"] = names.get(item.get(key)) if item.get(key) else None
        for entry in item.get("history", []):
            entry["by_name"] = names.get(entry.get("by"), "-")
    return items


def build_query(filters):
    query = {}
    if filters.get("status"):
        query["status"] = parse_enum(filters["status"], STATUSES, "status", "Status")
    if filters.get("request_type"):
        query["request_type"] = parse_enum(filters["request_type"], REQUEST_TYPES, "request_type", "Jenis")
    if filters.get("batch_id"):
        query["batch_id"] = parse_object_id(filters["batch_id"], "batch_id")
    bounds = utc_bounds(filters.get("date_from"), filters.get("date_to"))
    if bounds:
        query["submitted_at"] = bounds
    return query


def list_requests(db, filters, skip, limit, sort):
    query = build_query(filters)
    total = db.handling_requests.count_documents(query)
    items = list(db.handling_requests.find(query).sort(sort).skip(skip).limit(limit))
    return enrich(db, items), total


def get_request(db, request_id):
    return enrich(db, [_get(db, request_id)])[0]


def waiting_days(at, now=None):
    """Berapa hari sebuah pengajuan sudah menunggu (dipakai notifikasi dan dashboard)."""
    if not at:
        return 0
    now = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return max((now.astimezone(JAKARTA).date() - at.astimezone(JAKARTA).date()).days, 0)


REJECTED_NOTICE_DAYS = 7


def rejected_since():
    return (datetime.now(timezone.utc) - timedelta(days=REJECTED_NOTICE_DAYS)).replace(tzinfo=None)
