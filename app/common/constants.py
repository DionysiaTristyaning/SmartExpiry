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
#   > 30        -> normal
#   15 .. 30    -> monitoring
#   8 .. 14     -> near_expired
#   1 .. 7      -> critical
#   <= 0        -> expired  (barang tidak boleh dijual pada tanggal kedaluwarsanya)
MONITORING_DAYS = 30
NEAR_EXPIRED_DAYS = 14
CRITICAL_DAYS = 7

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
    "critical": 1,
    "near_expired": 3,
    "monitoring": 7,
    "normal": 7,
}
