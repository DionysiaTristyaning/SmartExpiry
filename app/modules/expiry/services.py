"""Status kedaluwarsa dan kelayakan batch. Keduanya TIDAK disimpan: selalu dihitung saat data dibaca (SD 5.4).

Batas status ditetapkan di kode (app/common/constants.py):
    sisa > 30 hari        -> normal
    15 sampai 30 hari     -> monitoring
    8 sampai 14 hari      -> near_expired
    1 sampai 7 hari       -> critical
    0 hari atau kurang    -> expired   (barang tidak boleh dijual pada tanggal kedaluwarsanya)

Kelayakan (SD 5.5 A) ditentukan dari PEMERIKSAAN TERAKHIR dan jumlah barang rusak yang belum ditangani:
    fit        -> sudah dicek dan tidak ada barang rusak
    partial    -> sebagian barang rusak (yang rusak dipisahkan; sisanya tetap boleh dijual)
    unfit      -> semua barang rusak, ATAU batch sudah Expired
    unchecked  -> belum pernah dicek (dan belum Expired)

Barang rusak (standar ritel: dipisahkan PER BUAH, bukan per batch):
    jumlah rusak = jumlah rusak pada pemeriksaan terakhir - jumlah yang sudah keluar lewat pengajuan
                   "barang rusak" setelah pemeriksaan itu.
    stok yang boleh dijual = stok - jumlah rusak (0 bila Expired).
"""
from datetime import date, timedelta

from ...common.constants import CHECK_INTERVAL_DAYS, CRITICAL_DAYS, MONITORING_DAYS, NEAR_EXPIRED_DAYS
from ...common.dates import JAKARTA

STATUSES = ("normal", "monitoring", "near_expired", "critical", "expired")

STATUS_LABELS = {
    "normal": "Aman",
    "monitoring": "Dipantau",
    "near_expired": "Hampir Kedaluwarsa",
    "critical": "Kritis",
    "expired": "Kedaluwarsa",
}

FITNESS_LABELS = {"fit": "Layak", "partial": "Sebagian rusak", "unfit": "Tidak layak", "unchecked": "Belum diperiksa"}

# Dasar pengajuan retur/pemusnahan (ditentukan dari kondisi batch, SD 5.5 C)
REQUEST_BASES = ("expired", "damaged", "near_expiry")
BASIS_LABELS = {"expired": "Barang kedaluwarsa", "damaged": "Barang rusak", "near_expiry": "Mendekati kedaluwarsa"}


def remaining_days(expiry, today):
    """expiry: date atau teks 'YYYY-MM-DD'."""
    if not isinstance(expiry, date):
        expiry = date.fromisoformat(expiry)
    return (expiry - today).days


def status_for_days(days):
    if days <= 0:
        return "expired"
    if days <= CRITICAL_DAYS:
        return "critical"
    if days <= NEAR_EXPIRED_DAYS:
        return "near_expired"
    if days <= MONITORING_DAYS:
        return "monitoring"
    return "normal"


def compute(expiry, today):
    days = remaining_days(expiry, today)
    return {"remaining_days": days, "expiry_status": status_for_days(days)}


def expiry_date_filter(status, today):
    """Ubah status menjadi rentang tanggal untuk query MongoDB (tanggal disimpan sebagai teks ISO)."""
    def iso(days):
        return (today + timedelta(days=days)).isoformat()

    if status == "expired":
        return {"$lte": iso(0)}
    if status == "critical":
        return {"$gt": iso(0), "$lte": iso(CRITICAL_DAYS)}
    if status == "near_expired":
        return {"$gt": iso(CRITICAL_DAYS), "$lte": iso(NEAR_EXPIRED_DAYS)}
    if status == "monitoring":
        return {"$gt": iso(NEAR_EXPIRED_DAYS), "$lte": iso(MONITORING_DAYS)}
    if status == "normal":
        return {"$gt": iso(MONITORING_DAYS)}
    raise ValueError(status)


def not_expired_filter(today):
    """Batch yang belum Expired (sisa hari >= 1)."""
    return {"$gt": today.isoformat()}


def latest_inspections(db, batch_ids):
    """Pemeriksaan terakhir untuk setiap batch: {batch_id: dokumen inspeksi}."""
    batch_ids = list(batch_ids)
    if not batch_ids:
        return {}
    latest = {}
    for item in db.inspections.find({"batch_id": {"$in": batch_ids}}).sort("inspected_at", -1):
        latest.setdefault(item["batch_id"], item)
    return latest


def _local_date(value):
    if getattr(value, "tzinfo", None) is None:
        from datetime import timezone
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(JAKARTA).date()


def check_schedule(status, current, received_date, latest_inspection, today):
    """Jadwal cek fisik (SD 5.5 A). Tanggal barang datang dihitung sebagai cek pertama.
    Batch Expired atau tanpa stok tidak dijadwalkan."""
    interval = CHECK_INTERVAL_DAYS.get(status)
    if not interval or current <= 0:
        return {"check_interval_days": None, "last_checked_date": None, "check_due": False, "days_since_check": None}
    last = _local_date(latest_inspection["inspected_at"]) if latest_inspection else date.fromisoformat(received_date)
    since = (today - last).days
    return {"check_interval_days": interval, "last_checked_date": last.isoformat(), "check_due": since >= interval,
            "days_since_check": since}


def inspection_damaged(inspection):
    """Jumlah barang rusak yang dicatat pada sebuah pemeriksaan.
    Data lama (sebelum ada kolom jumlah rusak): pemeriksaan "tidak layak" dianggap seluruh barang rusak."""
    if inspection is None:
        return 0
    if "damaged_quantity" in inspection:
        return inspection["damaged_quantity"] or 0
    return 0 if inspection.get("is_fit") else inspection.get("physical_quantity", 0)


def open_damaged(db, batches, latest):
    """{batch_id: jumlah rusak yang BELUM ditangani} untuk batch yang pemeriksaan terakhirnya mencatat barang rusak."""
    result = {}
    for batch in batches:
        inspection = latest.get(batch["_id"])
        damaged = inspection_damaged(inspection)
        if not damaged:
            continue
        handled = sum(m["quantity"] for m in db.stock_movements.find(
            {"batch_id": batch["_id"], "source.type": "handling_request", "source.basis": "damaged",
             "created_at": {"$gt": inspection["inspected_at"]}}, {"quantity": 1}))
        result[batch["_id"]] = max(0, min(damaged - handled, batch["current_quantity"]))
    return result


def fitness(status, latest_inspection, damaged=0, current=0):
    if status == "expired":
        return "unfit"
    if damaged > 0:
        return "unfit" if damaged >= current else "partial"
    if latest_inspection is None:
        return "unchecked"
    return "fit"


def sellable_quantity(status, current, damaged):
    """Stok yang boleh dicatat sebagai terjual: belum Expired, dikurangi barang rusak."""
    if status == "expired":
        return 0
    return max(0, current - damaged)


def request_options(status, current, damaged):
    """Pilihan pengajuan retur/pemusnahan untuk satu batch (keputusan pemilik 13-14 Nov 2026, direvisi 14 Nov):
    - expired     : batch Expired -> SELURUH stok, retur atau pemusnahan.
    - damaged     : ada barang rusak -> SEMUA barang rusak itu (jumlahnya tetap), retur atau pemusnahan.
    - near_expiry : batch Near Expired / Critical -> sebagian atau seluruh barang yang masih bagus, HANYA retur
                    (urutan ritel: jual -> retur -> musnahkan; barang layak tidak dibuang).
    Batch Normal / Monitoring yang tidak rusak tidak boleh diajukan (daftar kosong).
    """
    if current <= 0:
        return []
    if status == "expired":
        return [{"basis": "expired", "quantity": current, "fixed": True, "types": ["return", "disposal"]}]
    options = []
    if damaged > 0:
        options.append({"basis": "damaged", "quantity": damaged, "fixed": True, "types": ["return", "disposal"]})
    good = current - damaged
    if status in ("near_expired", "critical") and good > 0:
        options.append({"basis": "near_expiry", "quantity": good, "fixed": False, "types": ["return"]})
    return options
