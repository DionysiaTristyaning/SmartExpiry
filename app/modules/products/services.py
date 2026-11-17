"""Master produk (SD 5.2).

Aturan:
- SKU unik dan tidak dapat diubah setelah dibuat.
- Harga jual hanya informasi (tidak dipakai untuk transaksi atau diskon).
- Satuan besar (opsional), misalnya karton isi 24: hanya dipakai saat barang datang supaya Staff bisa mengisi
  sesuai surat jalan. Stok SELALU disimpan dalam satuan terkecil (`unit`).
- Stok minimum (titik pesan ulang): bila stok yang bisa dijual <= angka ini, produk masuk daftar "stok menipis".
  0 berarti produk tidak dipantau stok minimumnya.
- Produk yang sudah pernah memiliki batch tidak boleh dihapus permanen; hanya dapat dinonaktifkan.
"""
import re
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError, OperationFailure

from ...common.audit import log_action
from ...common.errors import Conflict, NotFound, ValidationFailed
from ...common.http import clean_text, parse_quantity

_SKU = re.compile(r"^[A-Z0-9][A-Z0-9_\-]{0,29}$")
MAX_PRICE = 1_000_000_000
MAX_MIN_STOCK = 100_000
MAX_PACK_SIZE = 10_000


def parse_price(value):
    """Harga jual: bilangan bulat rupiah >= 0, tanpa titik/koma."""
    return parse_quantity(value, "price", "Harga jual", max_value=MAX_PRICE, minimum=0)


def parse_min_stock(value):
    """Stok minimum: bilangan bulat >= 0. Kosong dianggap 0 (tidak dipantau)."""
    if value in (None, ""):
        return 0
    return parse_quantity(value, "min_stock", "Stok minimum", max_value=MAX_MIN_STOCK, minimum=0)


def parse_pack(data):
    """Satuan besar opsional: nama (misalnya karton) + isi (>= 2 satuan kecil). Keduanya diisi atau keduanya kosong."""
    pack_unit = clean_text(data, "pack_unit", "Satuan besar", max_len=20, required=False)
    raw = data.get("pack_size")
    if not pack_unit:
        if raw not in (None, "", 0, "0"):
            raise ValidationFailed("Isi juga nama satuan besarnya (misalnya karton), atau kosongkan isinya.",
                                   {"pack_unit": "Nama satuan besar belum diisi."})
        return "", 0
    size = parse_quantity(raw, "pack_size", "Isi per satuan besar", max_value=MAX_PACK_SIZE, minimum=2)
    return pack_unit, size


def validate_product(data, creating):
    """Periksa dan rapikan data produk. Mengembalikan dict siap simpan."""
    result = {}
    if creating:
        sku = clean_text(data, "sku", "Kode produk", max_len=30).upper()
        if not _SKU.match(sku):
            raise ValidationFailed("Kode produk hanya boleh berisi huruf, angka, tanda - dan _ (paling banyak 30).",
                                   {"sku": "Format kode produk tidak valid."})
        result["sku"] = sku
    result["name"] = clean_text(data, "name", "Nama produk", max_len=120)
    result["category"] = clean_text(data, "category", "Kategori", max_len=50)
    result["unit"] = clean_text(data, "unit", "Satuan", max_len=20)
    result["price"] = parse_price(data.get("price"))
    result["min_stock"] = parse_min_stock(data.get("min_stock"))
    result["pack_unit"], result["pack_size"] = parse_pack(data)
    result["description"] = clean_text(data, "description", "Deskripsi", max_len=500, required=False)
    return result


def _search(db, base_query, q, sort, skip, limit):
    """Pencarian: pakai indeks teks lebih dulu; jika tidak ada hasil, cari sebagian kata (SKU/nama)."""
    if q:
        try:
            query = {**base_query, "$text": {"$search": q}}
            total = db.master_product.count_documents(query)
            if total:
                return list(db.master_product.find(query).sort(sort).skip(skip).limit(limit)), total
        except (OperationFailure, NotImplementedError):
            pass  # indeks teks belum tersedia -> pakai pencarian sebagian kata
        pattern = {"$regex": re.escape(q), "$options": "i"}
        base_query = {**base_query, "$or": [{"sku": pattern}, {"name": pattern}]}
    total = db.master_product.count_documents(base_query)
    return list(db.master_product.find(base_query).sort(sort).skip(skip).limit(limit)), total


def list_products(db, q, category, is_active, skip, limit, sort):
    query = {}
    if category:
        query["category"] = category
    if is_active is not None:
        query["is_active"] = is_active
    items, total = _search(db, query, (q or "").strip()[:100], sort, skip, limit)
    return mark_deletable(db, items), total


def mark_deletable(db, items):
    """Tandai produk yang boleh dihapus permanen (belum pernah punya batch)."""
    used = set(db.batches.distinct("product_id", {"product_id": {"$in": [p["_id"] for p in items]}}))
    for item in items:
        item["has_batches"] = item["_id"] in used
    return items


def find_product_ids(db, q, limit=500):
    """Dipakai pencarian batch: ID produk yang cocok dengan kata kunci."""
    items, _ = _search(db, {}, q.strip()[:100], [("sku", 1)], 0, limit)
    return [item["_id"] for item in items]


def categories(db):
    return sorted(c for c in db.master_product.distinct("category") if c)


def get_product(db, product_id):
    product = db.master_product.find_one({"_id": product_id})
    if not product:
        raise NotFound("Produk tidak ditemukan.")
    return mark_deletable(db, [product])[0]


def create_product(db, actor, data):
    doc = validate_product(data, creating=True)
    if db.master_product.find_one({"sku": doc["sku"]}):
        raise Conflict("Kode produk sudah dipakai.", {"sku": "Kode produk sudah dipakai."})
    now = datetime.now(timezone.utc)
    doc.update({"is_active": True, "created_at": now, "updated_at": now, "created_by": actor["_id"], "updated_by": None})
    try:
        doc["_id"] = db.master_product.insert_one(doc).inserted_id
    except DuplicateKeyError:
        raise Conflict("Kode produk sudah dipakai.", {"sku": "Kode produk sudah dipakai."})
    log_action(db, actor, "product_created", "master_product", doc["_id"], details={"sku": doc["sku"]})
    return doc


def update_product(db, actor, product_id, data):
    old = get_product(db, product_id)
    changes = validate_product(data, creating=False)
    if "min_stock" not in data:
        changes.pop("min_stock")  # tidak dikirim -> nilai lama tetap dipakai
    if "pack_unit" not in data and "pack_size" not in data:
        changes.pop("pack_unit")
        changes.pop("pack_size")
    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            raise ValidationFailed("Status tidak valid.", {"is_active": "Status tidak valid."})
        changes["is_active"] = data["is_active"]
    changed = sorted(k for k, v in changes.items() if old.get(k) != v)
    changes.update({"updated_at": datetime.now(timezone.utc), "updated_by": actor["_id"]})
    db.master_product.update_one({"_id": product_id}, {"$set": changes})
    log_action(db, actor, "product_updated", "master_product", product_id,
               details={"sku": old["sku"], "changed_fields": changed})
    return get_product(db, product_id)


def delete_product(db, actor, product_id):
    product = get_product(db, product_id)
    if product["has_batches"]:
        raise Conflict("Produk ini sudah pernah punya stok, jadi tidak bisa dihapus. Ubah statusnya menjadi Nonaktif saja.")
    db.master_product.delete_one({"_id": product_id})
    log_action(db, actor, "product_deleted", "master_product", product_id, details={"sku": product["sku"]})
    return {"deleted": True}


def low_stock(db, active_only=True):
    """Produk aktif yang stok minimumnya diisi (> 0) dan stok layak jualnya <= stok minimum.
    Diurutkan dari yang paling kekurangan. Dihitung saat diminta, tidak disimpan."""
    from ..batches.services import sellable_by_product  # impor di sini: modul batches juga memakai modul ini

    query = {"min_stock": {"$gt": 0}}
    if active_only:
        query["is_active"] = True
    products = list(db.master_product.find(query))
    stock = sellable_by_product(db, [p["_id"] for p in products])
    rows = []
    for p in products:
        available = stock.get(p["_id"], 0)
        if available <= p["min_stock"]:
            rows.append({"product_id": p["_id"], "sku": p["sku"], "product_name": p["name"], "category": p["category"],
                         "unit": p["unit"], "min_stock": p["min_stock"], "available_stock": available,
                         "shortage": p["min_stock"] - available})
    rows.sort(key=lambda r: (-r["shortage"], r["sku"]))
    return rows
