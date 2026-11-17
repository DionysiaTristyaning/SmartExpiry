"""Sembilan laporan (SD 5.6) dan ekspornya ke Excel.

Semua angka dibaca langsung dari koleksi operasional (bukan tabel ringkasan terpisah), sehingga selalu konsisten
dengan riwayat pergerakan stok. Ekspor memakai fungsi yang SAMA dengan tampilan layar, jadi filternya identik,
berisi semua baris yang cocok (maksimal 20.000), dan setiap ekspor dicatat di audit log.
"""
from collections import defaultdict
from datetime import timezone

from ...common.audit import log_action
from ...common.dates import JAKARTA, parse_date_range, today_jakarta
from ...common.errors import NotFound, ValidationFailed
from ...common.http import parse_enum, parse_object_id
from ...common.xlsx import build_workbook
from ..batches import services as batch_services
from ..expiry import services as expiry
from ..inspections import services as inspection_services
from ..movements import services as movement_services
from ..movements.ledger import MOVEMENT_LABELS
from ..products import services as product_services
from ..requests import services as request_services

MAX_EXPORT_ROWS = 20000


# ---------- pembantu ----------

def _time(value):
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(JAKARTA).strftime("%Y-%m-%d %H:%M")


def _bool(value, name):
    if value in (None, ""):
        return None
    if value not in ("true", "false"):
        raise ValidationFailed(f"Parameter {name} harus true atau false.")
    return value == "true"


def _product_filter(args):
    return parse_object_id(args["product_id"], "product_id") if args.get("product_id") else None


def _days_text(row):
    days = row.get("remaining_days")
    if days is None:
        return ""
    return f"lewat {abs(days)} hari" if days < 0 else ("hari ini" if days == 0 else f"{days} hari")


# ---------- 1. stok produk ----------

def stock_products(db, args, skip, limit):
    today = today_jakarta()
    query = {}
    if args.get("category"):
        query["category"] = str(args["category"])[:50]
    active = _bool(args.get("is_active"), "is_active")
    if active is not None:
        query["is_active"] = active
    products = list(db.master_product.find(query).sort("sku", 1))
    totals = defaultdict(lambda: {"available_stock": 0, "expired_units": 0, "damaged_units": 0, "batch_count": 0,
                                  "nearest_expiry": None})
    batches = list(db.batches.find({"product_id": {"$in": [p["_id"] for p in products]}, "current_quantity": {"$gt": 0}}))
    for batch in batch_services.enrich(db, batches, today):
        t = totals[batch["product_id"]]
        t["batch_count"] += 1
        if batch["expiry_status"] == "expired":
            t["expired_units"] += batch["current_quantity"]
            continue
        t["damaged_units"] += batch["damaged_quantity"]
        t["available_stock"] += batch["sellable_quantity"]
        if batch["sellable_quantity"] and (t["nearest_expiry"] is None or batch["expiry_date"] < t["nearest_expiry"]):
            t["nearest_expiry"] = batch["expiry_date"]
    rows = []
    for p in products:
        t = totals[p["_id"]]
        min_stock = p.get("min_stock", 0)
        row = {"product_id": p["_id"], "sku": p["sku"], "product_name": p["name"], "category": p["category"],
               "unit": p["unit"], "price": p.get("price"), "is_active": p["is_active"], "min_stock": min_stock,
               "low_stock": bool(min_stock) and t["available_stock"] <= min_stock, **t}
        if t["nearest_expiry"]:
            row.update(expiry.compute(t["nearest_expiry"], today))
        rows.append(row)
    summary = {"products": len(rows), "available_stock": sum(r["available_stock"] for r in rows),
               "expired_units": sum(r["expired_units"] for r in rows),
               "damaged_units": sum(r["damaged_units"] for r in rows),
               "low_stock": sum(1 for r in rows if r["low_stock"] and r["is_active"])}
    return rows[skip:skip + limit], len(rows), summary


# ---------- 2. stok menipis ----------

def low_stock(db, args, skip, limit):
    rows = product_services.low_stock(db)
    if args.get("category"):
        rows = [r for r in rows if r["category"] == str(args["category"])[:50]]
    summary = {"products": len(rows), "shortage": sum(r["shortage"] for r in rows)}
    return rows[skip:skip + limit], len(rows), summary


# ---------- 3-5. laporan berbasis batch ----------

def _batch_report(db, query, skip, limit, summary_statuses):
    today = today_jakarta()
    total = db.batches.count_documents(query)
    summary = {s: {"batches": 0, "units": 0} for s in summary_statuses}
    for batch in db.batches.find(query, {"expiry_date": 1, "current_quantity": 1}):
        status = expiry.status_for_days(expiry.remaining_days(batch["expiry_date"], today))
        if status in summary:
            summary[status]["batches"] += 1
            summary[status]["units"] += batch["current_quantity"]
    items = list(db.batches.find(query).sort([("expiry_date", 1), ("batch_number", 1)]).skip(skip).limit(limit))
    return batch_services.enrich(db, items, today), total, summary


def stock_batches(db, args, skip, limit):
    query = {}
    product_id = _product_filter(args)
    if product_id:
        query["product_id"] = product_id
    if args.get("status"):
        parse_enum(args["status"], expiry.STATUSES, "status", "Status")
        query["expiry_date"] = expiry.expiry_date_filter(args["status"], today_jakarta())
    has_stock = _bool(args.get("has_stock"), "has_stock")
    if has_stock is True:
        query["current_quantity"] = {"$gt": 0}
    elif has_stock is False:
        query["current_quantity"] = 0
    return _batch_report(db, query, skip, limit, expiry.STATUSES)


def near_expiry(db, args, skip, limit):
    today = today_jakarta()
    statuses = ("near_expired", "critical")
    status = parse_enum(args.get("status"), statuses, "status", "Status", required=False)
    query = {"current_quantity": {"$gt": 0}}
    if status:
        query["expiry_date"] = expiry.expiry_date_filter(status, today)
    else:  # Near Expired + Critical = sisa 1..14 hari
        query["expiry_date"] = {"$gt": expiry.expiry_date_filter("critical", today)["$gt"],
                                "$lte": expiry.expiry_date_filter("near_expired", today)["$lte"]}
    product_id = _product_filter(args)
    if product_id:
        query["product_id"] = product_id
    return _batch_report(db, query, skip, limit, statuses)


def expired(db, args, skip, limit):
    query = {"current_quantity": {"$gt": 0}, "expiry_date": expiry.expiry_date_filter("expired", today_jakarta())}
    product_id = _product_filter(args)
    if product_id:
        query["product_id"] = product_id
    return _batch_report(db, query, skip, limit, ("expired",))


# ---------- 6-7. riwayat pergerakan ----------

def _movement_report(db, args, skip, limit, types):
    start, end = parse_date_range(args)
    filters = {"movement_type": args.get("movement_type", ""), "product_id": args.get("product_id", ""),
               "date_from": start, "date_to": end}
    query = movement_services.build_query(filters, allowed_types=types)
    total = db.stock_movements.count_documents(query)
    summary = {t: 0 for t in types}
    for m in db.stock_movements.find(query, {"movement_type": 1, "quantity": 1}):
        summary[m["movement_type"]] += m["quantity"]
    items = list(db.stock_movements.find(query).sort([("movement_date", -1), ("created_at", -1)]).skip(skip).limit(limit))
    return movement_services.enrich(db, items), total, summary


def movements_in_out(db, args, skip, limit):
    return _movement_report(db, args, skip, limit, ("stock_in", "stock_out"))


def adjustments(db, args, skip, limit):
    return _movement_report(db, args, skip, limit, ("adjustment_in", "adjustment_out"))


# ---------- 8. riwayat pemeriksaan ----------

def inspections(db, args, skip, limit):
    start, end = parse_date_range(args)
    filters = {"product_id": args.get("product_id", ""), "fitness": args.get("fitness", ""),
               "date_from": start, "date_to": end}
    query = inspection_services.build_query(filters)
    summary = {"inspections": db.inspections.count_documents(query),
               "unfit": db.inspections.count_documents({**query, "is_fit": False}),
               "corrections": db.inspections.count_documents({**query, "expiry_correction": {"$type": "object"}}),
               "with_difference": db.inspections.count_documents({"$and": [query, {"difference": {"$ne": 0}}]})}
    items, total = inspection_services.list_inspections(db, filters, skip, limit, [("inspected_at", -1)])
    return items, total, summary


# ---------- 9. riwayat pengajuan ----------

def requests(db, args, skip, limit):
    start, end = parse_date_range(args)
    filters = {"status": args.get("status", ""), "request_type": args.get("request_type", ""),
               "date_from": start, "date_to": end}
    query = request_services.build_query(filters)
    summary = {s: 0 for s in request_services.STATUSES}
    for r in db.handling_requests.find(query, {"status": 1}):
        summary[r["status"]] += 1
    items, total = request_services.list_requests(db, filters, skip, limit, [("submitted_at", -1)])
    return items, total, summary


# ---------- definisi laporan dan kolom ekspor ----------

STATUS = expiry.STATUS_LABELS
FIT = expiry.FITNESS_LABELS

_BATCH_COLUMNS = [
    ("Nomor Kiriman", lambda r: r.get("batch_number")),
    ("Kode Produk", lambda r: r.get("sku")),
    ("Produk", lambda r: r.get("product_name")),
    ("Tanggal Masuk", lambda r: r.get("received_date")),
    ("Tanggal Kedaluwarsa", lambda r: r.get("expiry_date")),
    ("Sisa Hari", lambda r: r.get("remaining_days")),
    ("Status", lambda r: STATUS.get(r.get("expiry_status"), "")),
    ("Jumlah Awal", lambda r: r.get("initial_quantity")),
    ("Stok Saat Ini", lambda r: r.get("current_quantity")),
    ("Rusak (belum ditangani)", lambda r: r.get("damaged_quantity")),
    ("Bisa Dijual", lambda r: r.get("sellable_quantity")),
    ("Satuan", lambda r: r.get("unit")),
    ("Kelayakan", lambda r: FIT.get(r.get("fitness"), "")),
]

_MOVEMENT_COLUMNS = [
    ("Tanggal", lambda r: r.get("movement_date")),
    ("Dicatat", lambda r: _time(r.get("created_at"))),
    ("Nomor Kiriman", lambda r: r.get("batch_number")),
    ("Kode Produk", lambda r: r.get("sku")),
    ("Produk", lambda r: r.get("product_name")),
    ("Jenis", lambda r: MOVEMENT_LABELS.get(r.get("movement_type"), "")),
    ("Perubahan", lambda r: r.get("signed_quantity")),
    ("Stok Sebelum", lambda r: r.get("quantity_before")),
    ("Stok Sesudah", lambda r: r.get("quantity_after")),
    ("Keterangan", lambda r: r.get("reason") or ""),
    ("Catatan", lambda r: r.get("notes") or ""),
    ("Dicatat Oleh", lambda r: r.get("created_by_name")),
]

REPORTS = {
    "stock-products": {
        "title": "Stok Produk", "fetch": stock_products,
        "columns": [
            ("Kode Produk", lambda r: r.get("sku")),
            ("Produk", lambda r: r.get("product_name")),
            ("Kategori", lambda r: r.get("category")),
            ("Satuan", lambda r: r.get("unit")),
            ("Harga Jual", lambda r: r.get("price")),
            ("Status Produk", lambda r: "Aktif" if r.get("is_active") else "Nonaktif"),
            ("Jumlah Kiriman Berstok", lambda r: r.get("batch_count")),
            ("Stok Minimum", lambda r: r.get("min_stock") or ""),
            ("Stok Bisa Dijual", lambda r: r.get("available_stock")),
            ("Stok Menipis", lambda r: "Ya" if r.get("low_stock") else ""),
            ("Barang Rusak", lambda r: r.get("damaged_units")),
            ("Barang Kedaluwarsa", lambda r: r.get("expired_units")),
            ("Kedaluwarsa Terdekat", lambda r: r.get("nearest_expiry") or ""),
            ("Sisa Hari", lambda r: r.get("remaining_days")),
        ],
    },
    "low-stock": {
        "title": "Stok Menipis", "fetch": low_stock,
        "columns": [
            ("Kode Produk", lambda r: r.get("sku")),
            ("Produk", lambda r: r.get("product_name")),
            ("Kategori", lambda r: r.get("category")),
            ("Satuan", lambda r: r.get("unit")),
            ("Stok Bisa Dijual", lambda r: r.get("available_stock")),
            ("Stok Minimum", lambda r: r.get("min_stock")),
            ("Kekurangan", lambda r: r.get("shortage")),
        ],
    },
    "stock-batches": {"title": "Stok per Kiriman", "fetch": stock_batches, "columns": _BATCH_COLUMNS},
    "near-expiry": {"title": "Mendekati Kedaluwarsa", "fetch": near_expiry, "columns": _BATCH_COLUMNS},
    "expired": {"title": "Produk Kedaluwarsa", "fetch": expired, "columns": _BATCH_COLUMNS},
    "movements": {"title": "Riwayat Stok Masuk dan Keluar", "fetch": movements_in_out, "columns": _MOVEMENT_COLUMNS},
    "adjustments": {"title": "Riwayat Penyamaan Stok", "fetch": adjustments, "columns": _MOVEMENT_COLUMNS},
    "inspections": {
        "title": "Riwayat Pemeriksaan", "fetch": inspections,
        "columns": [
            ("Waktu", lambda r: _time(r.get("inspected_at"))),
            ("Nomor Kiriman", lambda r: r.get("batch_number")),
            ("Kode Produk", lambda r: r.get("sku")),
            ("Produk", lambda r: r.get("product_name")),
            ("Stok Sistem", lambda r: r.get("system_quantity")),
            ("Jumlah Fisik", lambda r: r.get("physical_quantity")),
            ("Selisih", lambda r: r.get("difference")),
            ("Kondisi Produk", lambda r: inspection_services.CONDITION_LABELS.get(r.get("product_condition"), "")),
            ("Kondisi Kemasan", lambda r: inspection_services.CONDITION_LABELS.get(r.get("packaging_condition"), "")),
            ("Jumlah Rusak", lambda r: r.get("damaged_quantity")),
            ("Hasil", lambda r: "Layak" if r.get("is_fit") else "Ada yang rusak"),
            ("Tanggal di Kemasan", lambda r: (r.get("expiry_correction") or {}).get("proposed_date") or "Sesuai"),
            ("Koreksi Tanggal", lambda r: inspection_services.CORRECTION_STATUS_LABELS.get(
                (r.get("expiry_correction") or {}).get("status"), "")),
            ("Sudah Disesuaikan", lambda r: "Ya" if r.get("adjusted") else ("-" if r.get("difference") == 0 else "Belum")),
            ("Catatan", lambda r: r.get("notes")),
            ("Diperiksa Oleh", lambda r: r.get("inspected_by_name")),
        ],
    },
    "requests": {
        "title": "Riwayat Pengajuan", "fetch": requests,
        "columns": [
            ("Nomor", lambda r: r.get("request_number")),
            ("Diajukan", lambda r: _time(r.get("submitted_at"))),
            ("Jenis", lambda r: request_services.TYPE_LABELS.get(r.get("request_type"), "")),
            ("Barang", lambda r: r.get("basis_label")),
            ("Nomor Kiriman", lambda r: r.get("batch_number")),
            ("Kode Produk", lambda r: r.get("sku")),
            ("Produk", lambda r: r.get("product_name")),
            ("Jumlah Diajukan", lambda r: r.get("quantity")),
            ("Alasan", lambda r: r.get("reason")),
            ("Status", lambda r: request_services.STATUS_LABELS.get(r.get("status"), "")),
            ("Diajukan Oleh", lambda r: r.get("submitted_by_name")),
            ("Ditinjau Oleh", lambda r: r.get("reviewed_by_name") or ""),
            ("Waktu Tinjauan", lambda r: _time(r.get("reviewed_at"))),
            ("Catatan Peninjau", lambda r: r.get("review_note")),
            ("Jumlah Ditangani", lambda r: r.get("handled_quantity")),
            ("Diselesaikan Oleh", lambda r: r.get("completed_by_name") or ""),
            ("Waktu Selesai", lambda r: _time(r.get("completed_at"))),
            ("Dibatalkan Oleh", lambda r: r.get("cancelled_by_name") or ""),
            ("Catatan Pembatalan", lambda r: r.get("cancel_note")),
        ],
    },
}


def _spec(kind):
    spec = REPORTS.get(kind)
    if spec is None:
        raise NotFound("Laporan tidak dikenal.")
    return spec


def run(db, kind, args, skip, limit):
    return _spec(kind)["fetch"](db, args, skip, limit)


def export(db, user, kind, args):
    """Kembalikan (isi file .xlsx, nama file)."""
    spec = _spec(kind)
    items, total, _ = spec["fetch"](db, args, 0, MAX_EXPORT_ROWS)
    if total > MAX_EXPORT_ROWS:
        raise ValidationFailed(f"Data terlalu banyak untuk diunduh sekaligus ({total} baris, paling banyak "
                               f"{MAX_EXPORT_ROWS}). Pilih produk atau rentang tanggal yang lebih sempit dulu.")
    headers = [name for name, _ in spec["columns"]]
    rows = [[getter(item) for _, getter in spec["columns"]] for item in items]
    filters = {k: v for k, v in args.items() if v not in ("", None)}
    content = build_workbook(spec["title"], headers, rows)
    log_action(db, user, "report_exported", "reports", details={"kind": kind, "rows": len(rows), "filters": filters})
    return content, f"laporan-{kind}_{today_jakarta().isoformat()}.xlsx"
