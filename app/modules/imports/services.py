"""Impor CSV: master produk (Supervisor/Admin), stok awal / batch (Staff), dan rekap penjualan harian (Staff).
SD bagian 9.

Mode STRICT: semua baris divalidasi; jika ada satu saja yang salah, TIDAK ADA data yang disimpan.
Alur dua langkah: (1) preview = periksa dan tampilkan hasil, (2) confirm = periksa ulang lalu simpan
semua baris dalam satu transaksi.
Stok awal: setiap baris menjadi satu batch baru + satu stock_in. File yang sama (sidik jari SHA-256)
tidak dapat diimpor dua kali, sehingga stok tidak tercatat ganda.
Rekap penjualan: satu baris = satu produk + jumlah terjual (+ tanggal penjualan opsional, paling lama 7 hari ke belakang). Stok dikurangi otomatis mulai dari batch yang paling
cepat kedaluwarsa (sama seperti form Catat Terjual). File yang sama juga tidak dapat diimpor dua kali.
"""
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from ...common.audit import log_action
from ...common.dates import today_jakarta
from ...common.errors import Conflict, ValidationFailed
from ...common.http import clean_text, parse_quantity
from ...common.numbering import next_number, prefix_for
from ...common.transactions import transaction
from ..batches import services as batch_services
from ..movements import services as movement_services
from ..movements.ledger import record_movement
from ..products import services as product_services
from .csv_service import read_csv

PRODUCT_HEADERS = ["sku", "name", "category", "unit", "price", "min_stock", "pack_unit", "pack_size", "description"]
PRODUCT_REQUIRED = ["sku", "name", "category", "unit", "price"]
STOCK_HEADERS = ["sku", "quantity", "received_date", "expiry_date"]
SALES_HEADERS = ["sku", "quantity", "sale_date"]
SALES_REQUIRED = ["sku", "quantity"]
MAX_REPORTED_ERRORS = 100


def _report(total, errors, preview, applied, imported=0):
    error_rows = {e["row"] for e in errors}
    return {
        "total_rows": total,
        "invalid_rows": len(error_rows),
        "valid_rows": total - len(error_rows),
        "errors": errors[:MAX_REPORTED_ERRORS],
        "errors_truncated": len(errors) > MAX_REPORTED_ERRORS,
        "preview": preview[:10],
        "applied": applied,
        "imported": imported,
    }


# ---------- master produk ----------

def _validate_products(db, rows):
    errors, parsed, seen = [], [], {}
    for number, row, problem in rows:
        if problem:
            errors.append({"row": number, "message": problem})
            continue
        try:
            doc = product_services.validate_product(row, creating=True)
        except ValidationFailed as exc:
            errors.append({"row": number, "message": exc.message})
            continue
        if doc["sku"] in seen:
            errors.append({"row": number, "message": f"Kode produk {doc['sku']} ganda: sudah ada di baris {seen[doc['sku']]}."})
            continue
        seen[doc["sku"]] = number
        parsed.append((number, doc))
    existing = {p["sku"] for p in db.master_product.find({"sku": {"$in": list(seen)}}, {"sku": 1})}
    valid = []
    for number, doc in parsed:
        if doc["sku"] in existing:
            errors.append({"row": number, "message": f"Kode produk {doc['sku']} sudah terdaftar di aplikasi."})
        else:
            valid.append(doc)
    errors.sort(key=lambda e: e["row"])
    return errors, valid


def import_products(db, actor, upload, apply):
    rows, _ = read_csv(upload, PRODUCT_HEADERS, PRODUCT_REQUIRED)
    errors, valid = _validate_products(db, rows)
    report = _report(len(rows), errors, [dict(d) for d in valid], applied=False)
    if errors or not apply:
        return report
    now = datetime.now(timezone.utc)
    for doc in valid:
        doc.update({"is_active": True, "created_at": now, "updated_at": now, "created_by": actor["_id"],
                    "updated_by": None})
    with transaction(db) as session:
        db.master_product.insert_many(valid, session=session)
    log_action(db, actor, "csv_imported", "master_product", details={"kind": "products", "rows": len(valid)})
    return _report(len(rows), [], [], applied=True, imported=len(valid))


# ---------- stok awal / batch ----------

def _validate_stock(db, rows):
    today = today_jakarta()
    skus = {row["sku"].strip().upper() for _, row, _ in rows if row}
    products = {p["sku"]: p for p in db.master_product.find({"sku": {"$in": list(skus)}})}
    errors, valid, seen = [], [], {}
    for number, row, problem in rows:
        if problem:
            errors.append({"row": number, "message": problem})
            continue
        try:
            sku = clean_text(row, "sku", "Kolom sku (kode produk)", max_len=30).upper()
            product = products.get(sku)
            if not product:
                raise ValidationFailed(f"Kode produk {sku} belum terdaftar. Tambahkan dulu di Data Produk.")
            if not product.get("is_active"):
                raise ValidationFailed(f"Produk {sku} berstatus Nonaktif.")
            fields = batch_services.validate_stock_in_fields(row, today)
        except ValidationFailed as exc:
            errors.append({"row": number, "message": exc.message})
            continue
        key = (sku, fields["received_date"], fields["expiry_date"])
        if key in seen:
            errors.append({"row": number, "message": f"Baris ini sama persis dengan baris {seen[key]} (kode produk, tanggal datang, "
                                                     "dan tanggal kedaluwarsa sama). Gabungkan jumlahnya dalam satu baris."})
            continue
        seen[key] = number
        valid.append((product, fields))
    errors.sort(key=lambda e: e["row"])
    return errors, valid


def import_stock(db, actor, upload, apply):
    rows, fingerprint = read_csv(upload, STOCK_HEADERS, STOCK_HEADERS)
    if db.stock_movements.find_one({"source.file_sha256": fingerprint}, {"_id": 1}):
        raise Conflict("File ini sudah pernah dimasukkan, jadi stok tidak dicatat dua kali.")
    errors, valid = _validate_stock(db, rows)
    preview = [{"sku": p["sku"], "product_name": p["name"], **f} for p, f in valid]
    report = _report(len(rows), errors, preview, applied=False)
    if errors or not apply:
        return report

    now = datetime.now(timezone.utc)
    source = {"type": "csv_import", "file_sha256": fingerprint}
    created = []
    with transaction(db) as session:  # semua baris tersimpan bersama-sama atau tidak sama sekali
        taken = []
        try:
            for product, fields in valid:
                prefix = prefix_for("BT", datetime.fromisoformat(fields["received_date"]))
                number = next_number(db, "batches", "batch_number", prefix, taken=taken, session=session)
                taken.append(number)
                batch = {"_id": ObjectId(), "batch_number": number, "product_id": product["_id"],
                         "received_date": fields["received_date"], "expiry_date": fields["expiry_date"],
                         "initial_quantity": fields["quantity"], "current_quantity": 0,
                         "created_by": actor["_id"], "created_at": now, "updated_at": now}
                db.batches.insert_one(batch, session=session)
                created.append(batch["_id"])
                record_movement(db, batch, actor, "stock_in", fields["quantity"], movement_date=fields["received_date"],
                                source=source, session=session, now=now)
        except Exception:
            if session is None:  # tanpa transaksi: hapus yang sudah sempat dibuat
                db.batches.delete_many({"_id": {"$in": created}})
                db.stock_movements.delete_many({"batch_id": {"$in": created}})
            raise
    log_action(db, actor, "csv_imported", "batches",
               details={"kind": "stock", "rows": len(valid), "file_sha256": fingerprint})
    return _report(len(rows), [], [], applied=True, imported=len(valid))


# ---------- rekap penjualan harian ----------

def _validate_sales(db, rows):
    skus = {row["sku"].strip().upper() for _, row, _ in rows if row}
    products = {p["sku"]: p for p in db.master_product.find({"sku": {"$in": list(skus)}})}
    errors, valid, seen = [], [], {}
    for number, row, problem in rows:
        if problem:
            errors.append({"row": number, "message": problem})
            continue
        try:
            sku = clean_text(row, "sku", "Kode produk", max_len=30).upper()
            product = products.get(sku)
            if not product:
                raise ValidationFailed(f"Kode produk {sku} belum terdaftar.")
            if not product.get("is_active"):
                raise ValidationFailed(f"Produk {sku} berstatus Nonaktif.")
            if sku in seen:
                raise ValidationFailed(f"Kode produk {sku} sudah ada di baris {seen[sku]}. Gabungkan jumlahnya dalam satu baris.")
            quantity = parse_quantity(row.get("quantity"), "quantity", "Jumlah terjual",
                                      max_value=batch_services.MAX_QUANTITY)
            sale_date = movement_services.parse_sale_date(row.get("sale_date"))
            plan = movement_services.plan_sale(db, product, quantity, sale_date)
        except ValidationFailed as exc:
            errors.append({"row": number, "message": exc.message})
            continue
        seen[sku] = number
        valid.append((product, quantity, plan, sale_date))
    errors.sort(key=lambda e: e["row"])
    return errors, valid


def import_sales(db, actor, upload, apply):
    rows, fingerprint = read_csv(upload, SALES_HEADERS, SALES_REQUIRED)
    if db.stock_movements.find_one({"source.file_sha256": fingerprint}, {"_id": 1}):
        raise Conflict("File ini sudah pernah dimasukkan, jadi penjualan tidak dicatat dua kali.")
    errors, valid = _validate_sales(db, rows)
    preview = [{"sku": p["sku"], "product_name": p["name"], "quantity": q, "sale_date": d,
                "batches": ", ".join(f"{b['batch_number']} ({t})" for b, t, _ in plan)} for p, q, plan, d in valid]
    report = _report(len(rows), errors, preview, applied=False)
    if errors or not apply:
        return report

    source = {"type": "csv_import", "file_sha256": fingerprint}
    created = []
    with transaction(db) as session:  # semua baris tersimpan bersama-sama atau tidak sama sekali
        try:
            for _, _, plan, sale_date in valid:
                movement_services.apply_sale(db, actor, plan, source=source, sale_date=sale_date, session=session,
                                             out=created)
        except Exception:
            if session is None:  # tanpa transaksi: kembalikan stok yang sudah sempat dikurangi
                movement_services._undo(db, created)
            raise
    log_action(db, actor, "csv_imported", "stock_movements",
               details={"kind": "sales", "rows": len(valid), "file_sha256": fingerprint})
    return _report(len(rows), [], [], applied=True, imported=len(valid))


def template_csv(kind):
    """Isi file template CSV (dengan contoh baris)."""
    if kind == "products":
        return ("sku,name,category,unit,price,min_stock,pack_unit,pack_size,description\n"
                "P101,Susu UHT Cokelat 200 ml,Minuman,kotak,6500,24,karton,24,\n"
                "P102,Biskuit Gandum,Makanan Ringan,pcs,12000,10,,,Kemasan 100 g\n")
    if kind == "sales":
        yesterday = (today_jakarta() - timedelta(days=1)).isoformat()
        return f"sku,quantity,sale_date\nP001,12,{yesterday}\nP004,30,{yesterday}\n"
    today = today_jakarta()
    received, expiry = today.isoformat(), (today + timedelta(days=60)).isoformat()
    return ("sku,quantity,received_date,expiry_date\n"
            f"P001,48,{received},{expiry}\n"
            f"P002,30,{received},{expiry}\n")
