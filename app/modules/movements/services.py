"""Stok keluar (barang terjual) dan riwayat pergerakan stok (SD 5.3 B dan D).

- Stok keluar biasa berarti barang TERJUAL, jadi tidak ada kolom alasan.
- Cara utama: rekap penjualan PER PRODUK (misalnya rekap harian dari kasir). Sistem otomatis mengurangi stok
  mulai dari batch yang paling cepat kedaluwarsa (FEFO); bila batch itu tidak cukup, sisanya diambil dari batch
  berikutnya. Staff tidak perlu memilih nomor batch.
- Batch Expired dan barang rusak yang belum ditangani tidak pernah ikut "terjual"; barang itu hanya keluar
  lewat pengajuan retur/pemusnahan.
- Cara per batch (batch_id) tetap tersedia di API untuk kasus khusus.
- Riwayat pergerakan tidak dapat diubah atau dihapus.
"""
from datetime import timedelta

from ...common.audit import log_action
from ...common.constants import SALE_BACKDATE_DAYS
from ...common.dates import iso_bounds, parse_iso_date, today_jakarta
from ...common.errors import NotFound, ValidationFailed
from ...common.http import clean_text, parse_client_request_id, parse_enum, parse_object_id, parse_quantity
from ...common.transactions import transaction
from ..batches import services as batch_services
from .ledger import MOVEMENT_TYPES, ensure_new_client_request, record_movement


def parse_sale_date(value, field="sale_date"):
    """Tanggal penjualan: kosong = hari ini; boleh mundur paling lama SALE_BACKDATE_DAYS hari, tidak boleh besok."""
    today = today_jakarta()
    if value in (None, ""):
        return today.isoformat()
    day = parse_iso_date(value, field, "Tanggal penjualan")
    if day > today:
        raise ValidationFailed("Tanggal penjualan tidak boleh di masa depan.", {field: "Melewati hari ini."})
    if day < today - timedelta(days=SALE_BACKDATE_DAYS):
        raise ValidationFailed(f"Tanggal penjualan paling lama {SALE_BACKDATE_DAYS} hari ke belakang.",
                               {field: f"Maksimal {SALE_BACKDATE_DAYS} hari lalu."})
    return day.isoformat()


def plan_sale(db, product, quantity, sale_date=None):
    """Bagi jumlah terjual ke batch-batch layak jual, urut FEFO. Mengembalikan [(batch, jumlah, cadangan_rusak)].
    Batch yang datang SETELAH tanggal penjualan tidak ikut (barangnya belum ada di toko saat itu)."""
    batches = batch_services.fefo_batches(db, product["_id"])
    if sale_date:
        batches = [b for b in batches if b["received_date"] <= sale_date]
    available = sum(b["sellable_quantity"] for b in batches)
    if quantity > available:
        raise ValidationFailed(f"Stok {product['name']} yang bisa dijual hanya {available} {product.get('unit') or ''}"
                               .rstrip() + ". Periksa lagi jumlahnya.", {"quantity": f"Paling banyak {available}."})
    plan, left = [], quantity
    for batch in batches:
        if left <= 0:
            break
        take = min(left, batch["sellable_quantity"])
        if take > 0:
            plan.append((batch, take, batch["damaged_quantity"]))
            left -= take
    return plan


def apply_sale(db, actor, plan, *, source, sale_date=None, notes="", client_request_id=None, session=None, out=None):
    """Catat stok keluar untuk setiap bagian rencana penjualan. client_request_id hanya di pergerakan pertama.
    `out`: daftar penampung, supaya pemanggil tahu apa saja yang sudah tercatat bila terjadi kegagalan."""
    movements = out if out is not None else []
    for index, (batch, take, reserve) in enumerate(plan):
        movements.append(record_movement(
            db, batch, actor, "stock_out", take, movement_date=sale_date or today_jakarta().isoformat(), notes=notes,
            source=source, client_request_id=client_request_id if index == 0 else None, reserve=reserve,
            session=session))
    return movements


def _active_product(db, product_id):
    product = db.master_product.find_one({"_id": product_id})
    if not product or not product.get("is_active"):
        raise ValidationFailed("Produk tidak ditemukan atau tidak aktif.", {"product_id": "Produk tidak valid."})
    return product


def record_sale(db, actor, data):
    """Catat barang terjual per produk; stok dikurangi otomatis dari batch yang paling cepat kedaluwarsa."""
    client_request_id = parse_client_request_id(data)
    ensure_new_client_request(db, client_request_id)
    product = _active_product(db, parse_object_id(data.get("product_id"), "product_id"))
    quantity = parse_quantity(data.get("quantity"), "quantity", "Jumlah terjual", max_value=batch_services.MAX_QUANTITY)
    notes = clean_text(data, "notes", "Catatan", max_len=500, required=False)
    sale_date = parse_sale_date(data.get("sale_date"))
    plan = plan_sale(db, product, quantity, sale_date)
    created = []
    with transaction(db) as session:
        try:
            apply_sale(db, actor, plan, source={"type": "manual"}, sale_date=sale_date, notes=notes,
                       client_request_id=client_request_id, session=session, out=created)
        except Exception:
            if session is None:
                _undo(db, created)
            raise
    log_action(db, actor, "stock_out_recorded", "master_product", product["_id"],
               details={"sku": product["sku"], "quantity": quantity, "sale_date": sale_date,
                        "batch_number": ", ".join(f"{b['batch_number']} ({t})" for b, t, _ in plan)})
    return {"product_id": product["_id"], "sku": product["sku"], "product_name": product["name"],
            "unit": product.get("unit"), "quantity": quantity, "sale_date": sale_date, "movements": enrich(db, created)}


def _undo(db, movements):
    """Tanpa transaksi (database tiruan untuk tes): kembalikan stok bila pencatatan berhenti di tengah jalan."""
    for m in movements:
        db.batches.update_one({"_id": m["batch_id"]}, {"$inc": {"current_quantity": m["quantity"]}})
        db.stock_movements.delete_one({"_id": m["_id"]})


def record_stock_out(db, actor, data):
    """Stok keluar untuk SATU batch tertentu (kasus khusus). Barang rusak yang belum ditangani tidak ikut terjual."""
    client_request_id = parse_client_request_id(data)
    batch = batch_services.get_batch(db, parse_object_id(data.get("batch_id"), "batch_id"))
    quantity = parse_quantity(data.get("quantity"), "quantity", "Jumlah", max_value=batch_services.MAX_QUANTITY)
    notes = clean_text(data, "notes", "Catatan", max_len=500, required=False)

    if batch["expiry_status"] == "expired":
        raise ValidationFailed("Kiriman ini sudah kedaluwarsa dan tidak boleh dijual. Ajukan pengembalian atau pemusnahan.",
                               {"batch_id": "Kiriman kedaluwarsa."})
    if batch["fitness"] == "unfit":
        raise ValidationFailed("Pemeriksaan terakhir menyatakan kiriman ini rusak, sehingga tidak boleh dijual. "
                               "Ajukan pengembalian atau pemusnahan.", {"batch_id": "Kiriman tidak layak."})

    with transaction(db) as session:
        movement = record_movement(db, batch, actor, "stock_out", quantity, movement_date=today_jakarta().isoformat(),
                                   notes=notes, source={"type": "manual"}, client_request_id=client_request_id,
                                   reserve=batch["damaged_quantity"], session=session)
    log_action(db, actor, "stock_out_recorded", "stock_movements", movement["_id"],
               details={"batch_number": batch["batch_number"], "quantity": quantity})
    return enrich(db, [movement])[0]


def enrich(db, movements):
    batch_ids = {m["batch_id"] for m in movements}
    product_ids = {m["product_id"] for m in movements}
    user_ids = {m["created_by"] for m in movements if m.get("created_by")}
    batches = {b["_id"]: b for b in db.batches.find({"_id": {"$in": list(batch_ids)}}, {"batch_number": 1})}
    products = {p["_id"]: p for p in db.master_product.find({"_id": {"$in": list(product_ids)}},
                                                      {"sku": 1, "name": 1, "unit": 1})}
    users = {u["_id"]: u for u in db.master_karyawan.find({"_id": {"$in": list(user_ids)}}, {"name": 1})}
    request_ids = [m["source"]["handling_request_id"] for m in movements
                   if (m.get("source") or {}).get("handling_request_id")]
    requests = {r["_id"]: r for r in db.handling_requests.find({"_id": {"$in": request_ids}}, {"request_number": 1})}
    for m in movements:
        m["batch_number"] = batches.get(m["batch_id"], {}).get("batch_number")
        product = products.get(m["product_id"], {})
        m["sku"], m["product_name"], m["unit"] = product.get("sku"), product.get("name"), product.get("unit")
        m["created_by_name"] = users.get(m.get("created_by"), {}).get("name") or "-"
        m["signed_quantity"] = m["quantity"] if m["movement_type"] in ("stock_in", "adjustment_in") else -m["quantity"]
        source = m.get("source") or {}
        m["source_type"] = source.get("type")
        m["request_number"] = requests.get(source.get("handling_request_id"), {}).get("request_number")
    return movements


def build_query(filters, allowed_types=MOVEMENT_TYPES):
    query = {}
    movement_type = filters.get("movement_type")
    if movement_type:
        query["movement_type"] = parse_enum(movement_type, allowed_types, "movement_type", "Jenis pergerakan")
    else:
        query["movement_type"] = {"$in": list(allowed_types)}
    if filters.get("batch_id"):
        query["batch_id"] = parse_object_id(filters["batch_id"], "batch_id")
    if filters.get("product_id"):
        query["product_id"] = parse_object_id(filters["product_id"], "product_id")
    bounds = iso_bounds(filters.get("date_from"), filters.get("date_to"))
    if bounds:
        query["movement_date"] = bounds
    return query


def list_movements(db, filters, skip, limit, sort):
    query = build_query(filters)
    total = db.stock_movements.count_documents(query)
    items = list(db.stock_movements.find(query).sort(sort).skip(skip).limit(limit))
    return enrich(db, items), total


def get_movement(db, movement_id):
    movement = db.stock_movements.find_one({"_id": movement_id})
    if not movement:
        raise NotFound("Data tidak ditemukan.")
    return enrich(db, [movement])[0]
