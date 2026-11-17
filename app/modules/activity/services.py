"""Riwayat aktivitas (SD 5.6): menampilkan audit_logs. Hanya dapat dibaca; tidak ada ubah atau hapus."""
from ...common.dates import utc_bounds
from ...common.errors import ValidationFailed
from ...common.http import parse_object_id

ACTION_LABELS = {
    "login_success": "Masuk ke aplikasi",
    "login_failed": "Gagal masuk",
    "login_locked": "Akun dikunci sementara (salah password)",
    "logout": "Keluar dari aplikasi",
    "user_created": "Akun dibuat",
    "user_updated": "Akun diubah",
    "user_activated": "Akun diaktifkan",
    "user_deactivated": "Akun dinonaktifkan",
    "user_password_reset": "Password direset Admin",
    "password_changed": "Password diganti sendiri",
    "product_created": "Produk ditambah",
    "product_updated": "Produk diubah",
    "product_deleted": "Produk dihapus",
    "stock_in_recorded": "Barang datang",
    "receipt_rejected": "Barang datang ditolak seluruhnya",
    "stock_out_recorded": "Barang terjual",
    "stock_adjusted": "Stok disamakan",
    "inspection_recorded": "Cek fisik",
    "expiry_corrected": "Tanggal kedaluwarsa dikoreksi",
    "expiry_correction_rejected": "Koreksi tanggal ditolak",
    "request_submitted": "Pengajuan dibuat",
    "request_approved": "Pengajuan disetujui",
    "request_rejected": "Pengajuan ditolak",
    "request_cancelled": "Pengajuan dibatalkan",
    "request_completed": "Pengajuan diselesaikan",
    "csv_imported": "Impor dari file",
    "report_exported": "Unduh laporan Excel",
}


def build_query(filters):
    query = {}
    if filters.get("actor_id"):
        query["actor_id"] = parse_object_id(filters["actor_id"], "actor_id")
    if filters.get("action"):
        if filters["action"] not in ACTION_LABELS:
            raise ValidationFailed("Jenis aktivitas tidak valid.")
        query["action"] = filters["action"]
    bounds = utc_bounds(filters.get("date_from"), filters.get("date_to"))
    if bounds:
        query["created_at"] = bounds
    return query


def list_activity(db, filters, skip, limit):
    query = build_query(filters)
    total = db.audit_logs.count_documents(query)
    items = list(db.audit_logs.find(query).sort("created_at", -1).skip(skip).limit(limit))
    names = {u["_id"]: u["name"] for u in db.master_karyawan.find(
        {"_id": {"$in": list({i["actor_id"] for i in items if i.get("actor_id")})}}, {"name": 1})}
    for item in items:
        item["actor_name"] = names.get(item.get("actor_id"), "-")
        item["action_label"] = ACTION_LABELS.get(item["action"], item["action"])
    return items, total


def actors(db):
    return [{"id": str(u["_id"]), "name": u["name"]} for u in db.master_karyawan.find({}, {"name": 1}).sort("name", 1)]
