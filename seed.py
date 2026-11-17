"""Mengisi database dengan DATA CONTOH (demo) untuk SATU outlet, supaya aplikasi tidak kosong.

Cara pakai:
    py seed.py            -> tambah data contoh (aman dijalankan ulang, tidak menggandakan)
    py seed.py --reset    -> HAPUS semua data di database ini lalu isi ulang data contoh

Tanggal dibuat relatif terhadap hari seed dijalankan, sehingga semua status kedaluwarsa selalu ada.
"""
import argparse
import sys
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from werkzeug.security import generate_password_hash

from app.common.constants import ROLE_ADMIN, ROLE_STAFF, ROLE_SUPERVISOR
from app.common.dates import today_jakarta
from app.config import Config, missing_settings
from app.db import check_connection, create_database
from app.indexes import ensure_indexes
from app.modules.inspections.services import adjust_from_inspection, build_inspection
from app.modules.movements.ledger import record_movement
from app.modules.requests import services as requests

# Akun demo (ditentukan pemilik proyek, 14 Nov 2026). Pola: email = nama+peran@gmail.com, password = Nama+peran.
# Email tidak membedakan huruf besar/kecil saat login. Email ini hanya untuk demo; aplikasi tidak mengirim email.
# (nama, email, password, peran, aktif?)
USERS = [
    ("Budi", "budiadmin@gmail.com", "Budiadmin", ROLE_ADMIN, True),
    ("Andi", "andisupervisor@gmail.com", "Andisupervisor", ROLE_SUPERVISOR, True),
    ("Sari", "sarisupervisor@gmail.com", "Sarisupervisor", ROLE_SUPERVISOR, True),
    ("Rudi", "rudistaff@gmail.com", "Rudistaff", ROLE_STAFF, True),
    ("Rina", "rinastaff@gmail.com", "Rinastaff", ROLE_STAFF, True),
    ("Dewi", "dewistaff@gmail.com", "Dewistaff", ROLE_STAFF, True),
    ("Tono", "tonostaff@gmail.com", "Tonostaff", ROLE_STAFF, False),  # akun nonaktif: untuk demo login ditolak
]
PASSWORDS = {email: password for _, email, password, _, _ in USERS}

ADMIN_EMAIL = "budiadmin@gmail.com"
SUPERVISOR_EMAIL = "andisupervisor@gmail.com"
STAFF_EMAIL = "rudistaff@gmail.com"
STAFF2_EMAIL = "rinastaff@gmail.com"

# (SKU, nama, kategori, satuan, harga jual, stok minimum)
# Stok minimum = titik pesan ulang. Contoh yang sengaja menipis: Roti (P005), Sarden (P010), Jus (P013).
PRODUCTS = [
    ("P001", "Susu UHT Cokelat 250 ml", "Minuman", "kotak", 7000, 24),
    ("P002", "Biskuit Cokelat 120 g", "Makanan Ringan", "pcs", 9500, 12),
    ("P003", "Teh Botol 350 ml", "Minuman", "botol", 5000, 24),
    ("P004", "Mie Instan Goreng", "Makanan Instan", "pcs", 3500, 40),
    ("P005", "Roti Tawar Gandum", "Roti & Kue", "pcs", 16000, 10),
    ("P006", "Yogurt Stroberi Cup", "Susu & Olahan", "cup", 8000, 6),
    ("P007", "Keripik Kentang 68 g", "Makanan Ringan", "pcs", 11000, 12),
    ("P008", "Air Mineral 600 ml", "Minuman", "botol", 4000, 48),
    ("P009", "Kopi Susu Sachet", "Minuman", "sachet", 2000, 20),
    ("P010", "Sarden Kaleng 155 g", "Makanan Kaleng", "kaleng", 12500, 6),
    ("P011", "Saus Sambal 135 ml", "Bumbu", "botol", 9000, 0),
    ("P012", "Cokelat Batang 62 g", "Makanan Ringan", "pcs", 13000, 10),
    ("P013", "Jus Jeruk 200 ml", "Minuman", "kotak", 6000, 10),
    ("P014", "Sosis Siap Makan", "Makanan Instan", "pcs", 3000, 10),
    ("P015", "Keju Slice 10 lembar", "Susu & Olahan", "pak", 24000, 8),
]

# Satuan besar (opsional) untuk barang datang: SKU -> (nama satuan besar, isi)
PACKS = {"P001": ("karton", 24), "P003": ("krat", 24), "P004": ("dus", 40), "P008": ("karton", 24)}

# Barang ditolak saat datang (rusak waktu diterima): kunci batch -> (jumlah ditolak, alasan)
REJECTED_ON_ARRIVAL = {"teh-60": (2, "Dua botol retak saat diturunkan dari mobil, dikembalikan ke sopir")}

# (kunci, SKU, sisa hari sampai kedaluwarsa, jumlah awal, berapa hari lalu diterima)
BATCHES = [
    ("susu-10", "P001", 10, 30, 20), ("susu-90", "P001", 90, 40, 5),
    ("bisk-45", "P002", 45, 60, 15), ("bisk-1", "P002", 1, 7, 60),
    ("teh-5", "P003", 5, 24, 40), ("teh-60", "P003", 60, 48, 3),
    ("mie-180", "P004", 180, 100, 10),
    ("roti-2", "P005", 2, 12, 3),
    ("yog-0", "P006", -1, 8, 20), ("yog-9", "P006", 9, 16, 7),
    ("kerip-20", "P007", 20, 35, 30),
    ("air-365", "P008", 365, 120, 12),
    ("kopi-14", "P009", 14, 50, 25),
    ("sard-0", "P010", 0, 6, 90),
    ("saus-100", "P011", 100, 30, 8),
    ("cokl-30", "P012", 30, 25, 14),
    ("jus-3", "P013", -3, 10, 30),
    ("sos-12", "P014", 12, 14, 9), ("sos-6", "P014", 6, 11, 18),
    ("keju-3", "P015", 3, 9, 25), ("keju-80", "P015", 80, 28, 2),
]

# stok keluar (barang terjual): (kunci batch, jumlah)
SALES = [("susu-10", 2), ("teh-5", 4), ("yog-0", 3), ("bisk-45", 5), ("kopi-14", 10), ("cokl-30", 3)]

# pemeriksaan fisik: (kunci batch, email pemeriksa, selisih jumlah, kondisi produk, kondisi kemasan, jumlah rusak,
#                     tanggal di kemasan beda (sisa hari) atau None, catatan, langsung disesuaikan?)
INSPECTIONS = [
    ("susu-10", STAFF_EMAIL, 0, "baik", "baik", 0, None, "", False),
    ("bisk-45", STAFF2_EMAIL, -1, "baik", "baik", 0, None, "Satu bungkus tidak ditemukan di rak", True),
    ("teh-5", STAFF_EMAIL, -1, "baik", "baik", 0, None, "Kurang satu botol saat dihitung", False),
    ("roti-2", STAFF2_EMAIL, 0, "baik", "rusak", 3, None, "Plastik kemasan sobek pada 3 bungkus, sudah dipisahkan", False),
    ("keju-3", SUPERVISOR_EMAIL, 0, "baik", "baik", 0, None, "", False),
    ("cokl-30", STAFF_EMAIL, 0, "baik", "baik", 0, 12,
     "Tanggal di kemasan ternyata 12 hari lagi, bukan 30 hari (salah ketik saat barang datang)", False),
]


def _user(db, email):
    return db.master_karyawan.find_one({"email": email})


def seed_users(db):
    now = datetime.now(timezone.utc)
    added = 0
    for name, email, password, role, active in USERS:
        if db.master_karyawan.find_one({"email": email}):
            continue
        db.master_karyawan.insert_one({"name": name, "email": email, "password_hash": generate_password_hash(password), "role": role,
                             "is_active": active, "last_login_at": None, "created_at": now, "updated_at": now,
                             "created_by": None})
        added += 1
    return added


def seed_products(db):
    now = datetime.now(timezone.utc)
    admin = _user(db, ADMIN_EMAIL)
    added = 0
    for sku, name, category, unit, price, min_stock in PRODUCTS:
        if db.master_product.find_one({"sku": sku}):
            continue
        db.master_product.insert_one({"sku": sku, "name": name, "category": category, "unit": unit, "price": price,
                                "min_stock": min_stock,
                                "pack_unit": PACKS.get(sku, ("", 0))[0], "pack_size": PACKS.get(sku, ("", 0))[1],
                                "description": "", "is_active": True, "created_at": now, "updated_at": now,
                                "created_by": admin["_id"], "updated_by": None})
        added += 1
    return added


def seed_operations(db):
    """Batch, stok keluar, pemeriksaan, dan pengajuan. Hanya diisi bila belum ada batch sama sekali."""
    if db.batches.count_documents({}) > 0:
        return {}
    today = today_jakarta()
    now = datetime.now(timezone.utc)
    staff1, staff2 = _user(db, STAFF_EMAIL), _user(db, STAFF2_EMAIL)
    supervisor = _user(db, SUPERVISOR_EMAIL)
    batches = {}
    counters = {}

    # --- batch + stok masuk (dibuat langsung agar batch yang sudah kedaluwarsa pun bisa dicontohkan) ---
    for key, sku, days, quantity, received_ago in BATCHES:
        product = db.master_product.find_one({"sku": sku})
        received = today - timedelta(days=received_ago)
        prefix = f"BT-{received:%y%m%d}-"
        counters[prefix] = counters.get(prefix, 0) + 1
        batch = {"_id": ObjectId(), "batch_number": f"{prefix}{counters[prefix]:03d}", "product_id": product["_id"],
                 "received_date": received.isoformat(), "expiry_date": (today + timedelta(days=days)).isoformat(),
                 "initial_quantity": quantity, "current_quantity": 0, "created_by": staff1["_id"],
                 "received_quantity": quantity + REJECTED_ON_ARRIVAL.get(key, (0, ""))[0],
                 "rejected_quantity": REJECTED_ON_ARRIVAL.get(key, (0, ""))[0],
                 "reject_reason": REJECTED_ON_ARRIVAL.get(key, (0, ""))[1], "pack": None,
                 "created_at": now, "updated_at": now}
        db.batches.insert_one(batch)
        record_movement(db, batch, staff1, "stock_in", quantity, movement_date=batch["received_date"],
                        source={"type": "manual"}, now=now)
        batches[key] = batch

    # --- stok keluar (terjual) ---
    for key, quantity in SALES:
        record_movement(db, batches[key], staff2, "stock_out", quantity, movement_date=today.isoformat(),
                        source={"type": "manual"})

    # --- pemeriksaan fisik (dicatat setelah penjualan, jadi selisihnya masih berlaku) ---
    inspections = {}
    for key, email, diff, product_cond, pack_cond, damaged, label_days, notes, adjust in INSPECTIONS:
        batch = db.batches.find_one({"_id": batches[key]["_id"]})
        inspector = _user(db, email)
        label_date = (today + timedelta(days=label_days)).isoformat() if label_days is not None else None
        fields = {"physical_quantity": batch["current_quantity"] + diff, "product_condition": product_cond,
                  "packaging_condition": pack_cond, "damaged_quantity": damaged,
                  "expiry_label": "different" if label_date else "match", "label_expiry_date": label_date,
                  "notes": notes}
        doc = build_inspection(batch, inspector, fields, datetime.now(timezone.utc))
        doc["_id"] = db.inspections.insert_one(doc).inserted_id
        inspections[key] = doc
        if adjust:
            adjust_from_inspection(db, inspector, doc["_id"])

    # --- pengajuan dalam semua status ---
    def submit(key, request_type, quantity, reason, actor=staff1, basis=None):
        return requests.submit(db, actor, {"batch_id": str(batches[key]["_id"]), "request_type": request_type,
                                           "quantity": quantity, "reason": reason, "basis": basis,
                                           "client_request_id": str(uuid.uuid4())})

    submit("jus-3", "disposal", 10, "Jus jeruk sudah lewat tanggal kedaluwarsa 3 hari")
    approved = submit("roti-2", "return", 3, "Kemasan sobek 3 bungkus, dikembalikan ke pemasok", staff2, "damaged")
    requests.review(db, supervisor, approved["_id"], "approve", {"note": "Setuju, pisahkan dulu dari rak"})
    completed = submit("sard-0", "disposal", 6, "Sarden kedaluwarsa hari ini")
    requests.review(db, supervisor, completed["_id"], "approve", {"note": "Setuju"})
    requests.complete(db, staff2, completed["_id"], {"handled_quantity": 6, "note": "Kemasan dirusak lalu dibuang ke bak sampah belakang, disaksikan Andi (Supervisor)"})
    rejected = submit("yog-0", "return", 5, "Yogurt kedaluwarsa, coba dikembalikan ke pemasok")
    requests.review(db, supervisor, rejected["_id"], "reject",
                    {"note": "Pemasok tidak menerima pengembalian barang kedaluwarsa. Ajukan pemusnahan."})
    cancelled = submit("sos-6", "return", 4, "Salah pilih kiriman", staff2)
    requests.cancel(db, staff2, cancelled["_id"], {"note": "Salah input, seharusnya kiriman lain"})

    return {"batch": len(batches), "stok keluar": len(SALES), "pemeriksaan": len(inspections), "pengajuan": 5}


def main():
    parser = argparse.ArgumentParser(description="Isi database dengan data contoh.")
    parser.add_argument("--reset", action="store_true", help="hapus SEMUA data di database ini terlebih dahulu")
    args = parser.parse_args()

    missing = missing_settings(Config)
    if missing:
        sys.exit("File .env belum lengkap (" + ", ".join(missing) + " masih kosong). Lihat README.md.")

    db = create_database(Config.MONGO_URI, Config.DATABASE_NAME)
    problem = check_connection(db)
    if problem:
        sys.exit("Gagal terhubung ke database.\n" + problem)

    if args.reset:
        print(f"PERINGATAN: semua data di database '{Config.DATABASE_NAME}' akan DIHAPUS.")
        if input("Ketik YA (huruf besar) untuk melanjutkan: ").strip() != "YA":
            sys.exit("Dibatalkan. Tidak ada yang diubah.")
        for name in db.list_collection_names():
            db.drop_collection(name)

    ensure_indexes(db)
    user_added = seed_users(db)
    product_added = seed_products(db)
    operations = seed_operations(db)

    print(f"Selesai. Baru ditambahkan -> pengguna: {user_added}, produk: {product_added}"
          + "".join(f", {k}: {v}" for k, v in operations.items()) + ".")
    if not (user_added or product_added or operations):
        print("Data contoh sudah ada, tidak ada yang ditambahkan.")
    print("\nAkun demo:")
    for name, email, password, role, active in USERS:
        print(f"  {name:<5} {role:<11} {email:<26} password: {password:<15} {'aktif' if active else 'NONAKTIF'}")


if __name__ == "__main__":
    main()
