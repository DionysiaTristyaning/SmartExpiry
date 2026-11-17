"""Nilai tetap aplikasi (SD 2.0). Peran dan batas status kedaluwarsa sengaja ditetapkan di kode,
tidak dapat diubah dari aplikasi."""

# ---------- peran (SD bagian 4) ----------
ROLE_ADMIN = "admin"
ROLE_SUPERVISOR = "supervisor"
ROLE_STAFF = "staff"

ROLES = (ROLE_ADMIN, ROLE_SUPERVISOR, ROLE_STAFF)

ROLE_LABELS = {
    ROLE_ADMIN: "Admin",
    ROLE_SUPERVISOR: "Supervisor",
    ROLE_STAFF: "Staff",
}

# ---------- batas status kedaluwarsa (SD 5.4) ----------
# sisa_hari = tanggal kedaluwarsa - hari ini (WIB)
#   > 90        -> normal
#   31 .. 90    -> monitoring (perlu dipantau berkala, sekitar 2-3 bulan sebelum kedaluwarsa)
#   1 .. 30     -> critical   (1 bulan terakhir; pembeli umumnya sudah enggan membeli)
#   <= 0        -> expired    (barang tidak boleh dijual pada tanggal kedaluwarsanya)
MONITORING_DAYS = 90
CRITICAL_DAYS = 30

# ---------- keamanan login (SD 11.1) ----------
# Setelah MAX_FAILED_LOGINS kali salah password berturut-turut, akun dikunci sementara selama LOGIN_LOCK_MINUTES.
# Angka ini mengikuti kebiasaan umum aplikasi (5 kali, 15 menit).
MAX_FAILED_LOGINS = 5
LOGIN_LOCK_MINUTES = 15
# Sesi berakhir bila tidak ada aktivitas pengguna selama sekian menit (komputer toko dipakai bergantian).
IDLE_TIMEOUT_MINUTES = 30

# ---------- barang terjual ----------
# Rekap penjualan boleh dicatat untuk hari ini atau mundur paling lama sekian hari (misalnya rekap kemarin).
SALE_BACKDATE_DAYS = 7

# ---------- pemberitahuan ----------
# Penyesuaian stok ditampilkan ke Supervisor dan Admin selama sekian hari (pengawasan, bukan persetujuan).
ADJUSTMENT_NOTICE_DAYS = 7

# ---------- jadwal cek fisik (SD 5.5 A) ----------
# Batch yang masih ada stoknya harus dicek fisik paling lambat setiap sekian hari, tergantung statusnya.
# Tanggal barang datang dihitung sebagai cek pertama (barang diperiksa saat diterima).
# Batch Expired tidak dijadwalkan: barangnya harus ditarik dan diajukan retur/pemusnahan.
CHECK_INTERVAL_DAYS = {
    "critical": 3,
    "monitoring": 14,
    "normal": 14,
}
