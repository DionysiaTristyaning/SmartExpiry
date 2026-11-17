"""Ringkasan dashboard (SD 5.1). Semua angka dihitung langsung dari database saat diminta.

- Stok tersedia = stok yang BOLEH DIJUAL: batch belum Expired, dikurangi barang rusak yang belum ditangani.
- Jumlah batch per status hanya menghitung batch dengan stok > 0.
- Perlu cek fisik (Staff, Supervisor) = batch yang sudah waktunya dicek menurut jadwal (SD 5.5 A).
- Stok menipis = produk aktif yang stok tersedianya <= stok minimum (stok minimum diisi > 0).
- Supervisor dan Admin juga melihat jumlah penyesuaian stok 7 hari terakhir yang belum dicek ulang Supervisor
  (pengawasan); Supervisor melihat usulan koreksi tanggal yang menunggu keputusannya.
"""
from datetime import datetime, timedelta, timezone

from ...common.constants import ADJUSTMENT_NOTICE_DAYS, ROLE_ADMIN, ROLE_STAFF, ROLE_SUPERVISOR
from ..batches import services as batch_services
from ..expiry import services as expiry
from ..products import services as product_services


def adjustments_since():
    return (datetime.now(timezone.utc) - timedelta(days=ADJUSTMENT_NOTICE_DAYS)).replace(tzinfo=None)


def unreviewed_adjustments(db):
    """Penyesuaian stok 7 hari terakhir yang BELUM dicek ulang. Pemberitahuan ini hilang begitu seorang Supervisor
    mencatat cek fisik pada kiriman yang sama sesudah penyesuaian itu (itulah pengawasannya). Penyesuaian
    lama tetap bisa dilihat di Laporan dan Riwayat Aktivitas."""
    moves = list(db.stock_movements.find(
        {"source.type": "inspection", "created_at": {"$gte": adjustments_since()}}).sort("created_at", -1))
    if not moves:
        return []
    supervisors = [u["_id"] for u in db.master_karyawan.find({"role": ROLE_SUPERVISOR}, {"_id": 1})]
    checks = list(db.inspections.find(
        {"batch_id": {"$in": [m["batch_id"] for m in moves]}, "inspected_by": {"$in": supervisors}},
        {"batch_id": 1, "inspected_at": 1}))
    return [m for m in moves
            if not any(c["batch_id"] == m["batch_id"] and c["inspected_at"] > m["created_at"] for c in checks)]


def summary(db, user):
    by_status = {status: 0 for status in expiry.STATUSES}
    available_stock = expired_units = damaged_units = 0
    for batch in batch_services.enrich(db, list(db.batches.find({"current_quantity": {"$gt": 0}}))):
        by_status[batch["expiry_status"]] += 1
        if batch["expiry_status"] == "expired":
            expired_units += batch["current_quantity"]
        else:
            damaged_units += batch["damaged_quantity"]
            available_stock += batch["sellable_quantity"]

    result = {
        "total_active_products": db.master_product.count_documents({"is_active": True}),
        "total_available_stock": available_stock,
        "expired_units": expired_units,
        "damaged_units": damaged_units,
        "low_stock_products": len(product_services.low_stock(db)),
        "by_status": by_status,
        "pending_requests": db.handling_requests.count_documents({"status": "pending"}),
    }
    if user["role"] in (ROLE_STAFF, ROLE_SUPERVISOR):
        from ..expiry.alerts import due_for_check
        result["check_due"] = len(due_for_check(db))
    if user["role"] == ROLE_STAFF:
        result["approved_open_requests"] = db.handling_requests.count_documents({"status": "approved"})
    if user["role"] in (ROLE_SUPERVISOR, ROLE_ADMIN):
        result["recent_adjustments"] = len(unreviewed_adjustments(db))
        result["adjustment_days"] = ADJUSTMENT_NOTICE_DAYS
    if user["role"] == ROLE_SUPERVISOR:
        result["pending_corrections"] = db.inspections.count_documents({"expiry_correction.status": "pending"})
    return result
