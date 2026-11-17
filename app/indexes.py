"""Daftar indeks MongoDB (SD bagian 8). Dibuat otomatis saat aplikasi dijalankan (aman diulang).

Indeks mempercepat pencarian dan menjaga data tetap unik, termasuk mencegah transaksi stok tercatat dua kali.
Indeks "sparse" hanya berlaku untuk dokumen yang memiliki field tersebut.
"""
from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import OperationFailure

# (nama koleksi, daftar kunci, opsi)
INDEXES = [
    # --- master_karyawan (akun dan peran) ---
    ("master_karyawan", [("email", ASCENDING)], {"unique": True, "name": "uniq_email"}),
    # --- master_product (data induk produk) ---
    ("master_product", [("sku", ASCENDING)], {"unique": True, "name": "uniq_sku"}),
    ("master_product", [("name", TEXT), ("sku", TEXT)], {"name": "text_products"}),
    ("master_product", [("category", ASCENDING), ("is_active", ASCENDING)], {"name": "category_active"}),
    # --- batches ---
    ("batches", [("batch_number", ASCENDING)], {"unique": True, "name": "uniq_batch_number"}),
    ("batches", [("product_id", ASCENDING), ("expiry_date", ASCENDING)], {"name": "product_expiry_fefo"}),
    ("batches", [("expiry_date", ASCENDING), ("current_quantity", ASCENDING)], {"name": "expiry_quantity"}),
    # --- stock_movements (append-only) ---
    ("stock_movements", [("batch_id", ASCENDING), ("created_at", DESCENDING)], {"name": "batch_created"}),
    ("stock_movements", [("movement_type", ASCENDING), ("movement_date", DESCENDING)], {"name": "type_date"}),
    ("stock_movements", [("client_request_id", ASCENDING)],
     {"unique": True, "sparse": True, "name": "uniq_movement_client_request"}),
    ("stock_movements", [("source.handling_request_id", ASCENDING)],
     {"unique": True, "sparse": True, "name": "uniq_movement_per_request"}),
    ("stock_movements", [("source.inspection_id", ASCENDING)],
     {"unique": True, "sparse": True, "name": "uniq_adjustment_per_inspection"}),
    ("stock_movements", [("source.file_sha256", ASCENDING)], {"sparse": True, "name": "import_file"}),
    # --- inspections (append-only) ---
    ("inspections", [("batch_id", ASCENDING), ("inspected_at", DESCENDING)], {"name": "batch_inspected"}),
    ("inspections", [("inspected_at", DESCENDING)], {"name": "inspected_at"}),
    ("inspections", [("client_request_id", ASCENDING)],
     {"unique": True, "sparse": True, "name": "uniq_inspection_client_request"}),
    # --- handling_requests ---
    ("handling_requests", [("request_number", ASCENDING)], {"unique": True, "name": "uniq_request_number"}),
    ("handling_requests", [("client_request_id", ASCENDING)], {"unique": True, "name": "uniq_request_client_request"}),
    ("handling_requests", [("status", ASCENDING), ("submitted_at", DESCENDING)], {"name": "status_submitted"}),
    ("handling_requests", [("batch_id", ASCENDING), ("basis", ASCENDING), ("status", ASCENDING)],
     {"name": "batch_basis_status"}),
    # --- inspections: usulan koreksi tanggal yang menunggu ---
    ("inspections", [("expiry_correction.status", ASCENDING)], {"sparse": True, "name": "expiry_correction_status"}),
    # --- audit_logs (append-only) ---
    ("audit_logs", [("created_at", DESCENDING)], {"name": "audit_created"}),
    ("audit_logs", [("actor_id", ASCENDING), ("created_at", DESCENDING)], {"name": "audit_actor"}),
    ("audit_logs", [("entity", ASCENDING), ("entity_id", ASCENDING)], {"name": "audit_entity"}),
]


def _drop_conflicting(coll, keys, options):
    """Hapus indeks lama yang bentrok (kunci sama atau nama sama) sebelum dibuat ulang."""
    wanted_key = list(keys)
    for info in coll.list_indexes():
        name = info["name"]
        if name == "_id_":
            continue
        same_keys = list(info["key"].items()) == wanted_key
        if same_keys or name == options["name"]:
            coll.drop_index(name)


def ensure_indexes(db, skip_text=False):
    """Buat semua indeks. skip_text=True dipakai pada database tiruan untuk pengujian."""
    created = []
    for collection, keys, options in INDEXES:
        if skip_text and any(direction == TEXT for _, direction in keys):
            continue
        try:
            db[collection].create_index(keys, **options)
        except OperationFailure as exc:
            # 85 = indeks sama sudah ada dengan nama lain; 86 = nama sama tapi opsi beda.
            if exc.code not in (85, 86):
                raise
            _drop_conflicting(db[collection], keys, options)
            db[collection].create_index(keys, **options)
        created.append(f"{collection}.{options['name']}")
    return created
