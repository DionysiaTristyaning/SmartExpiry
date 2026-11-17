"""Aturan rekomendasi (rule-based; TIDAK memakai AI atau machine learning). SD 5.5 B.

Setiap batch dengan stok > 0 mendapat TEPAT SATU rekomendasi: aturan pertama yang cocok dari atas ke bawah.
  1. Expired                                     -> Tarik dari area penjualan, ajukan retur/pemusnahan
  2. Ada barang rusak yang belum ditangani        -> Pisahkan barang yang rusak saja, ajukan retur/pemusnahan
                                                    untuk barang rusak itu; sisanya tetap boleh dijual
  3. Critical                                    -> Prioritaskan penanganan: keluarkan lebih dulu (FEFO); bila tidak
                                                    akan terjual, retur ke pemasok selagi masih layak
  4. Near Expired                                -> Prioritaskan penjualan berdasarkan FEFO
  5. Monitoring                                  -> Pantau dan prioritaskan penjualan berdasarkan FEFO
  6. Normal                                      -> Tidak membutuhkan tindakan khusus

Tidak ada rekomendasi diskon. Rekomendasi hanya SARAN: tidak mengubah stok dan tidak menjalankan tindakan.
"""
from datetime import timezone

from ...common.dates import JAKARTA

# kode: (urutan, label, perlu pengajuan retur/pemusnahan?)
ACTIONS = {
    "withdraw": (1, "Ambil dari rak, ajukan penanganan", True),
    "separate": (2, "Pisahkan barang rusak", True),
    "prioritize_handling": (3, "Segera tangani", False),
    "prioritize_sale": (4, "Jual lebih dulu", False),
    "monitor_fefo": (5, "Pantau", False),
    "no_action": (6, "Tidak perlu tindakan", False),
}

CONDITION_TEXT = {"baik": "baik", "rusak": "rusak"}


def _result(action, reason):
    priority, label, needs_request = ACTIONS[action]
    return {"action": action, "action_label": label, "priority": priority, "needs_request": needs_request,
            "reason": reason}


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def _date_text(value):
    if value is None:
        return "-"
    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(JAKARTA)
    return f"{local.day} {_MONTHS[local.month - 1]} {local.year}"


def _fefo_text(batch):
    rank, total = batch.get("fefo_rank"), batch.get("fefo_total")
    if rank == 1 and total and total > 1:
        return f" Dari {total} kiriman produk ini, kiriman inilah yang paling cepat kedaluwarsa."
    if rank and total and total > 1:
        return f" Urutan jual ke-{rank} dari {total} kiriman produk ini (yang paling cepat kedaluwarsa dijual duluan)."
    return ""


def recommend(batch):
    """`batch`: dokumen batch yang sudah diperkaya (status, sisa hari, pemeriksaan terakhir, urutan FEFO)."""
    status = batch["expiry_status"]
    days = batch["remaining_days"]
    last = batch.get("last_inspection")

    if status == "expired":
        when = "hari ini" if days == 0 else f"{-days} hari yang lalu"
        return _result("withdraw", f"Sudah kedaluwarsa ({when}) dan tidak boleh dijual. Ambil dari rak, "
                                   "lalu ajukan pengembalian ke pemasok atau pemusnahan.")

    damaged = batch.get("damaged_quantity", 0)
    if damaged:
        unit = batch.get("unit") or "unit"
        good = batch.get("current_quantity", damaged) - damaged
        rest = f" Sisanya ({good} {unit}) masih bagus dan tetap boleh dijual." if good > 0 else ""
        seen = (f"Cek fisik {_date_text(last['inspected_at'])}: kondisi produk "
                f"{CONDITION_TEXT.get(last['product_condition'])}, kemasan "
                f"{CONDITION_TEXT.get(last['packaging_condition'])}. ") if last else ""
        return _result("separate",
                       f"{seen}Ada {damaged} {unit} yang rusak. Pisahkan yang rusak dari rak, lalu ajukan "
                       f"pengembalian atau pemusnahan untuk barang rusak itu.{rest}")

    if status == "critical":
        check = (f" Pemeriksaan terakhir {_date_text(last['inspected_at'])}: layak." if last
                 else " Belum dicek; lakukan pemeriksaan fisik dulu.")
        return _result("prioritize_handling",
                       f"Sisa {days} hari. Taruh di depan rak supaya terjual lebih dulu.{check}{_fefo_text(batch)} "
                       "Bila tidak akan terjual sebelum kedaluwarsa, ajukan pengembalian ke pemasok selagi masih layak.")

    if status == "near_expired":
        return _result("prioritize_sale", f"Sisa {days} hari. Usahakan kiriman ini terjual lebih dulu.{_fefo_text(batch)}")

    if status == "monitoring":
        return _result("monitor_fefo", f"Sisa {days} hari. Pantau, dan jual yang paling cepat kedaluwarsa lebih dulu.{_fefo_text(batch)}")

    return _result("no_action", f"Sisa {days} hari. Belum perlu tindakan apa pun.")
