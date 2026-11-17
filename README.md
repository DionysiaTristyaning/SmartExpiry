# Sistem Monitoring Stok dan Kedaluwarsa Produk pada Satu Outlet

Aplikasi web (Flask + MongoDB Atlas + Webix) untuk mencatat stok **satu outlet** per batch, memantau tanggal kedaluwarsa, mencatat pemeriksaan fisik, memberi rekomendasi berbasis aturan, dan mengatur pengajuan retur/pemusnahan yang disetujui Supervisor.

Rancangan lengkap: `SD/SD_Smart_Expiry_Stock_Management_System.md` dan `SD/SRS_Smart_Expiry_Stock_Management_System.md` (versi 2.1).

---

## Sebelum mulai

- Panduan ini ditulis untuk **Windows**. Jika perintah `py` tidak dikenali, Python belum terpasang: pasang dari python.org dan centang "Add Python to PATH".
- Semua perintah dijalankan di **terminal yang terbuka di folder project ini** (folder yang berisi file `main.py`). Caranya: di File Explorer buka folder project, klik kolom alamat, ketik `powershell`, lalu tekan Enter.
- Bagian **A** hanya untuk **pertama kali**. Untuk hari-hari berikutnya cukup bagian **C**.
- Satu-satunya file yang perlu diisi adalah **`.env`** (dua baris). File itu rahasia: jangan dikirim atau dibagikan ke siapa pun karena berisi password database.
- Ingin tahu cara kerja aplikasi, alat yang dipakai, atau di mana ketentuan dosen terpenuhi? Lihat bagian **G**.

---

## A. Pertama kali saja (setup awal)

### A1. Buat "venv" (kotak khusus untuk alat-alat Python)
```
py -m venv venv
```
Tunggu sampai selesai (bisa 1 menit). Akan muncul folder baru bernama `venv`.

> Jika di folder sudah ada folder `venv` bawaan dari orang lain, **hapus dulu folder `venv` itu**, lalu jalankan perintah di atas. Venv tidak bisa dipindah antar komputer.

### A2. Masuk ke venv
PowerShell:
```
.\venv\Scripts\Activate.ps1
```
CMD (Command Prompt):
```
venv\Scripts\activate.bat
```
Berhasil jika di awal baris terminal muncul tulisan `(venv)`.

Jika PowerShell menolak dengan tulisan *"running scripts is disabled"*, jalankan sekali ini saja, lalu ulangi perintah masuk venv:
```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
(Jawab `Y` jika ditanya.)

### A3. Pasang semua alat yang dibutuhkan
```
pip install -r requirements.txt
```
Ini hanya dilakukan **sekali**. Tunggu sampai muncul tulisan `Successfully installed ...`.

### A4. Siapkan kredensial (kunci rahasia dan alamat database)

Buka file **`.env`** (klik kanan, buka dengan Notepad). Ada dua baris yang harus terisi:

```
SECRET_KEY=
MONGO_URI=
```

**Isi `SECRET_KEY`** (kunci rahasia untuk mengamankan login). Buat dengan perintah ini, lalu salin hasilnya setelah tanda `=` tanpa spasi:
```
py -c "import secrets; print(secrets.token_hex(32))"
```
Hasilnya berupa huruf dan angka acak yang panjang. Contoh: `SECRET_KEY=3f9a...c1`.

**Isi `MONGO_URI`** (alamat database di MongoDB Atlas). Langkah di situs MongoDB Atlas (https://cloud.mongodb.com), masuk dengan akun yang sudah ada:

1. **Buat cluster gratis** (jika belum ada): klik *Create* / *Build a Database*, pilih paket **M0 (Free)**, pilih region terdekat, klik *Create*.
2. **Buat user database**: menu *Database Access* → *Add New Database User*. Isi username dan password (pakai huruf dan angka saja agar mudah; catat). Beri izin *Read and write to any database*. Simpan.
3. **Izinkan komputer ini mengakses**: menu *Network Access* → *Add IP Address* → klik **Add Current IP Address** → *Confirm*.
   (Jika nanti ganti jaringan/wifi dan muncul error koneksi, ulangi langkah ini.)
4. **Ambil alamat koneksi**: menu *Database* → tombol *Connect* pada cluster → pilih *Drivers* → salin teks yang diawali `mongodb+srv://...`.
5. Pada teks itu, **ganti tulisan `<password>` dengan password user database dari langkah 2** (hilangkan tanda `<` `>`).
6. Tempel hasilnya ke `.env`, **diapit tanda kutip dua**:
   ```
   MONGO_URI="mongodb+srv://namauser:passwordnya@cluster0.xxxxx.mongodb.net/"
   ```

Simpan file `.env`. Baris lain di `.env` biarkan seperti adanya.

> `.env` itu rahasia. Jangan dikirim ke orang lain, jangan di-upload ke GitHub.

### A5. Isi data contoh (seed)
```
py seed.py
```
**Apa gunanya?** Database yang baru dibuat itu kosong, jadi tidak ada akun untuk login. Perintah ini mengisi **data contoh** satu outlet (akun dengan peran berbeda, 15 produk, 21 batch dengan berbagai tanggal kedaluwarsa, pemeriksaan, dan pengajuan) supaya aplikasi langsung bisa dicoba dan didemokan. Cukup dijalankan **sekali**. Kalau terlanjur dijalankan lagi, tidak apa-apa: data tidak akan dobel.

> Jika database Atlas-mu masih berisi data **versi lama** (yang memakai lokasi LOC001/LOC002/LOC003, atau koleksi bernama `users` dan `products` dari sebelum 16 November 2026), jalankan `py seed.py --reset` supaya datanya diganti dengan data versi baru. Nama koleksi sekarang `master_karyawan` dan `master_product`; bila namanya belum diganti, aplikasi tidak menemukan akun dan semua login ditolak.

Untuk menghapus semua data lalu mengisi ulang dari awal (hati-hati, semua data terhapus):
```
py seed.py --reset
```
(Akan diminta mengetik `YA` sebagai konfirmasi.)

Di akhir akan tampil daftar akun demo. Setiap akun punya **password sendiri** (huruf besar/kecil berpengaruh). Email boleh ditulis dengan huruf besar atau kecil.

| Email | Password | Nama | Peran |
|---|---|---|---|
| budiadmin@gmail.com | `Budiadmin` | Budi | Admin |
| andisupervisor@gmail.com | `Andisupervisor` | Andi | Supervisor |
| sarisupervisor@gmail.com | `Sarisupervisor` | Sari | Supervisor |
| rudistaff@gmail.com | `Rudistaff` | Rudi | Staff |
| rinastaff@gmail.com | `Rinastaff` | Rina | Staff |
| dewistaff@gmail.com | `Dewistaff` | Dewi | Staff |
| tonostaff@gmail.com | `Tonostaff` | Tono | Staff (akun dinonaktifkan, untuk mencoba bahwa login ditolak) |

> Email ini hanya untuk demo. Aplikasi tidak pernah mengirim email.

### A6. Jalankan aplikasi pertama kali
Lihat bagian **C**.

---

## B. Jika ada error

| Tulisan di terminal | Artinya / yang dilakukan |
|---|---|
| `File .env belum lengkap ... SECRET_KEY` atau `MONGO_URI masih kosong` | Isi dua baris itu di `.env` (langkah A4), simpan, jalankan ulang. |
| `Tidak bisa terhubung ke MongoDB Atlas ...` | Alamat IP komputer belum diizinkan di Atlas (A4 langkah 3), atau internet bermasalah. |
| `Username atau password database salah` | Password di `MONGO_URI` tidak sama dengan password user database di Atlas. Periksa lagi (A4 langkah 2 dan 5). |
| `Format MONGO_URI salah` | Salin ulang alamat dari Atlas. Pastikan diapit tanda kutip dua dan `<password>` sudah diganti. |
| `'py' is not recognized` | Python belum terpasang atau belum masuk PATH. Pasang dari python.org dengan mencentang "Add Python to PATH". |
| `ModuleNotFoundError` | Belum masuk venv (A2) atau belum menjalankan `pip install -r requirements.txt` (A3). |
| `Address already in use` | Aplikasi sebelumnya masih jalan. Tutup terminal lama atau tekan `Ctrl+C` di sana. |

---

## C. Menjalankan aplikasi sehari-hari (setelah setup awal selesai)

Tidak perlu membuat venv, `pip install`, atau mengubah `.env` lagi. Cukup:

1. Buka terminal di folder project (File Explorer → klik kolom alamat → ketik `powershell` → Enter).
2. Masuk ke venv:
   - PowerShell: `.\venv\Scripts\Activate.ps1`
   - CMD: `venv\Scripts\activate.bat`
3. Jalankan server:
   ```
   py main.py
   ```
4. Buka browser ke **http://127.0.0.1:5000** lalu login dengan salah satu akun demo di atas.
5. Untuk berhenti: tekan `Ctrl+C` di terminal.

---

## D. Yang sudah ada di aplikasi saat ini (versi 2.1, satu outlet)

> **Istilah di layar vs di dokumen.** Di layar aplikasi dipakai bahasa sehari-hari yang baku; di README, SD, dan SRS dipakai istilah teknisnya. Padanan: **Batch = Kiriman** (menu *Stok Barang*), Normal = *Aman*, Monitoring = *Dipantau*, Near Expired = *Hampir Kedaluwarsa*, Critical = *Kritis*, Expired = *Kedaluwarsa*, Retur = *Pengembalian* (ke pemasok), penyesuaian stok = *Stok disamakan*, SKU = *Kode produk*. Tabel lengkap ada di awal SD.

**Hanya fitur di bawah ini yang sudah selesai dan diuji (265 tes otomatis):**

- **Login dan logout**: password disimpan sebagai hash, akun nonaktif ditolak, sesi berakhir setelah 8 jam. **Salah password 5 kali berturut-turut → akun dikunci 15 menit** (Admin bisa membuka dengan mengganti password). **Keluar otomatis setelah 30 menit tanpa aktivitas** (komputer toko dipakai bergantian). Setiap pengguna bisa **mengganti password sendiri** (klik nama di kanan atas); akun baru atau yang direset Admin **wajib** membuat password sendiri saat masuk, jadi Admin tidak tahu password siapa pun.
- **Tiga peran** dengan hak akses yang dicek di server:
  - **Admin** (admin **sistem**, bukan admin gudang): mengelola akun (tambah, ubah peran, aktifkan/nonaktifkan, atur ulang password) dan master produk; melihat semua data, laporan, dan riwayat aktivitas; **memantau penyesuaian stok** lewat lonceng. Tidak mencatat stok dan tidak menyetujui pengajuan (pemisahan tugas).
  - **Supervisor**: hak master produk sama dengan Admin; menyetujui atau menolak pengajuan dan **usulan koreksi tanggal kedaluwarsa**; memeriksa fisik barang (cek silang); melihat laporan dan riwayat aktivitas. Tidak mencatat stok.
  - **Staff**: mencatat stok masuk dan keluar, memeriksa fisik, menyesuaikan stok dari hasil pemeriksaan, mengajukan retur/pemusnahan, lalu menandai pengajuan selesai.
- **Master produk**: SKU, nama, kategori, satuan, **harga jual** (informasi saja), **stok minimum** (batas pesan ulang), deskripsi, status. Produk yang sudah punya batch tidak bisa dihapus, cukup dinonaktifkan.
- **Stok masuk**: setiap penerimaan menjadi **batch baru** dengan nomor otomatis (misalnya `BT-261112-001`). Sebelum disimpan ada **layar konfirmasi**, karena data batch tidak dapat diubah langsung (tanggal kedaluwarsa hanya bisa dikoreksi lewat cek fisik + persetujuan Supervisor). Barang yang sudah kedaluwarsa (termasuk yang kedaluwarsa hari ini) tidak dapat dicatat.
- **Barang datang per karton**: produk boleh punya satuan besar (misalnya karton isi 24). Staff mengisi "3 karton + 5" sesuai surat jalan, sistem menghitung 77. Stok tetap dihitung per satuan terkecil.
- **Barang rusak saat datang ditolak**: isi "Jumlah ditolak" dan alasannya. Barang itu dikembalikan ke pengirim, tidak masuk stok, tetapi tetap tercatat. Kalau semua ditolak, tidak ada batch, tetapi kejadiannya tercatat di Riwayat Aktivitas.
- **Barang terjual** (tanpa alasan) dicatat **per produk**, misalnya rekap kasir harian: pilih produk, **tanggal penjualan** (hari ini atau sampai 7 hari lalu), isi total terjual. Sistem otomatis mengurangi stok dari batch yang **paling cepat kedaluwarsa** (FEFO), lanjut ke batch berikutnya bila kurang. Barang **Expired atau rusak tidak pernah ikut terjual**. Bisa juga lewat **Impor File** rekap penjualan (kode produk + jumlah).
- **Pemeriksaan fisik** (Staff dan Supervisor): jumlah fisik, kondisi produk, kondisi kemasan, **berapa yang rusak**, **tanggal di kemasan sesuai atau tidak**, catatan. Pemeriksaan tidak mengubah stok.
- **Jadwal cek fisik**: Critical dicek tiap hari, Near Expired tiap 3 hari, lainnya tiap 7 hari. Yang sudah waktunya muncul di **Pantau Kedaluwarsa → Perlu dicek**, di dashboard Staff, dan di lonceng Staff.
- **Barang rusak dihitung per buah** (standar ritel): kalau 2 dari 24 botol penyok, hanya 2 itu yang harus diretur/dimusnahkan; 22 lainnya tetap boleh dijual.
- **Koreksi tanggal kedaluwarsa**: kalau tanggal di kemasan berbeda dengan yang tercatat, cek fisik mengirim usulan; **Supervisor lain** menyetujui atau menolak; tanggal lama tetap tersimpan di riwayat.
- **Penyesuaian stok**: bila hasil hitung berbeda, Staff menekan **"Samakan stok"** dan stok langsung disesuaikan tanpa persetujuan. Jumlahnya otomatis dari selisih, satu pemeriksaan hanya bisa dipakai sekali, dan ditolak bila stok sudah berubah sejak pemeriksaan. Setiap penyesuaian **muncul di lonceng Supervisor dan Admin** (paling lama 7 hari) dan hilang setelah Supervisor mengecek fisik kiriman itu, jadi selalu diawasi.
- **Status kedaluwarsa** dihitung otomatis per batch (zona waktu Jakarta): Normal (> 30 hari), Monitoring (15–30), Near Expired (8–14), Critical (1–7), **Expired (0 hari atau lewat)**. Barang tidak boleh dijual pada tanggal kedaluwarsanya.
- **Monitoring kedaluwarsa**: daftar batch Monitoring sampai Expired yang masih berstok, yang terdekat di atas.
- **Saran Tindakan** (rekomendasi) berbasis aturan (bukan AI), satu per batch, lengkap dengan alasan: ambil dari rak dan ajukan penanganan (Expired), pisahkan barang rusak, segera tangani (Critical), jual lebih dulu (Near Expired), pantau (Monitoring), atau tidak perlu tindakan (Normal). **Tidak ada diskon.**
- **Lapor barang rusak langsung**: Staff yang menemukan barang rusak (termasuk dari produk yang belum kedaluwarsa) cukup membuka **Pengajuan > + Ajukan**, memilih produk dan kiriman, memilih **Lapor barang rusak**, lalu mengisi jumlah dan alasan. Jumlah itu langsung **ditahan** (tidak bisa dijual) sampai pengajuannya selesai atau ditolak. Tidak perlu Cek Fisik dulu.
- **Pengajuan retur/pemusnahan** (urutan ala ritel: **jual → retur → musnahkan**): untuk **barang Expired** (seluruh batch), **barang rusak** (semua yang rusak), atau barang **Near Expired/Critical** yang masih bagus (boleh sebagian, **hanya retur**, karena barang layak tidak dimusnahkan). Staff mengajukan → Supervisor menyetujui atau menolak (alasan wajib) → barang ditangani di luar aplikasi → Staff mana pun menandai **Selesai** dengan **keterangan bukti wajib** (retur: pemasok dan nomor dokumen; pemusnahan: cara dan saksi) → sistem **otomatis** mencatat stok keluar. Pengajuan tidak bisa bertumpuk: barang Expired baru bisa diajukan setelah pengajuan lain di batch yang sama selesai atau dibatalkan. Pengajuan bisa **dibatalkan** (oleh pengaju saat masih menunggu, atau oleh Supervisor setelah disetujui). Setiap langkah tercatat di riwayat.
- **Tombol Panduan** (di atas, sebelah lonceng): tugas sehari-hari sesuai peran yang sedang login dan di menu mana mengerjakannya, plus arti status kedaluwarsa. Setiap form utama juga punya keterangan singkat di bagian atas dan petunjuk di bawah isian.
- **Notifikasi lonceng** (di dalam aplikasi, bukan email/WhatsApp): Supervisor melihat pengajuan yang menunggu, usulan koreksi tanggal, dan penyesuaian stok yang belum dicek ulang; Admin melihat penyesuaian stok yang belum dicek ulang; Staff melihat pengajuan yang disetujui tapi belum selesai dan pengajuannya yang ditolak.
- **Dashboard**: produk aktif, stok yang boleh dijual, jumlah batch per status, pengajuan menunggu, **stok menipis**, **barang rusak**, (Supervisor/Admin) penyesuaian 7 hari, (Supervisor) koreksi tanggal menunggu, dan (Staff) pengajuan yang belum diselesaikan.
- **9 laporan** (Supervisor dan Admin) dengan filter dan **ekspor Excel (.xlsx)**: stok produk, **stok menipis**, stok per batch, mendekati kedaluwarsa, kedaluwarsa, riwayat stok masuk/keluar, riwayat penyesuaian, riwayat pemeriksaan, riwayat pengajuan.
- **Riwayat aktivitas** (Supervisor dan Admin): siapa melakukan apa dan kapan. Tidak dapat diubah atau dihapus.
- **Impor File** (CSV dari Excel): data produk (Supervisor/Admin), stok awal dan rekap penjualan harian (Staff). Semua baris diperiksa dulu; satu baris salah berarti tidak ada yang disimpan. File stok/penjualan yang sama tidak bisa diimpor dua kali.
- **Pencegahan stok tercatat dua kali**: setiap form punya ID unik, jadi klik ganda atau kirim ulang ditolak.
- **Tampilan responsif**: tabel di laptop, kartu per baris di HP.
- Perlindungan CSRF, validasi dan sanitasi input, audit log, dan indeks MongoDB yang dibuat otomatis.

### Yang BELUM ada atau sengaja tidak dibuat (supaya tidak salah menjelaskan ke dosen)

- Multi-outlet, gudang, dan transfer stok (sengaja: aplikasi untuk **satu outlet**).
- Kasir/POS, diskon, bundling, AI, notifikasi email/WhatsApp (sengaja, di luar ruang lingkup).
- Produk yang tidak punya tanggal kedaluwarsa (sabun, alat tulis): sengaja tidak dicatat di aplikasi ini.
- Pemesanan ke pemasok dan data pemasok (aplikasi untuk **toko**, bukan gudang/pembelian): aplikasi hanya memberi tahu stok menipis; pemesanan dilakukan di luar aplikasi.
- Aplikasi online (deploy): disiapkan untuk Vercel, langkahnya di bagian I. Sehari-hari tetap berjalan di komputer sendiri (bagian C).

---

## E. Skenario demo (contoh urutan untuk presentasi)

Email dan password akun ada di tabel bagian A5. Urutan ini cocok dengan data contoh `py seed.py` dan juga dengan data demo yang sudah diringkas (8 produk, tanpa pengajuan) di database yang dipakai saat presentasi. Pengajuan dibuat langsung pada langkah 5, jadi langkah 6 dan 7 punya bahan untuk ditunjukkan.

1. Login **rudistaff@gmail.com** (Rudi, Staff). Dashboard menampilkan produk aktif, stok tersedia, batch per status, dan pengajuan.
2. **Stok Barang → + Barang Datang**: pilih Susu UHT (punya satuan karton), isi 3 karton + 5, ditolak 2 dengan alasan "kotak penyok", lalu tunjukkan **layar konfirmasi** (datang 77, ditolak 2, masuk stok 75, status dan sisa hari). Batch baru mendapat nomor otomatis. Lalu buka **Pantau Kedaluwarsa → Perlu dicek** untuk menunjukkan jadwal cek fisik.
3. **Keluar-Masuk Stok → + Catat Terjual**: pilih Susu UHT, isi jumlah yang lebih besar dari batch terdekat; form menunjukkan stok diambil dari batch terdekat lalu batch berikutnya (**FEFO otomatis**). Coba Jus Jeruk atau Roti Tawar (keduanya Expired): **ditolak** ("yang bisa dijual hanya 0"), karena barang kedaluwarsa tidak boleh dijual.
4. **Pemeriksaan Stok**: cari baris yang punya selisih (misalnya Teh Botol, -1) dan klik **Samakan stok**; stok langsung berubah tanpa persetujuan (nanti muncul di lonceng Supervisor/Admin sampai Supervisor mengecek fisik kirimannya). Klik **+ Cek Fisik** untuk menunjukkan isiannya: jumlah hasil hitung, ada yang rusak (berapa dan bagian apa), tanggal di kemasan, catatan. Untuk menunjukkan **koreksi tanggal**, pilih tanggal di kemasan "Berbeda dengan catatan" lalu isi tanggal lain; usulan itu menunggu persetujuan Supervisor.
5. **Saran Tindakan**: tunjukkan saran dan alasannya. Pada Yogurt yang Expired, klik **Buat pengajuan** (pemusnahan).
6. Keluar, login **andisupervisor@gmail.com** (Andi, Supervisor). Dashboard menunjukkan **Stok menipis**, **Barang rusak**, **Stok disamakan**, dan **Koreksi tanggal**. Lonceng menunjukkan pengajuan yang menunggu: buka, lalu **Setujui** (atau **Tolak** dengan alasan). Bila ada usulan koreksi tanggal dari langkah 4, buka **Pemeriksaan Stok** dan klik **Setujui tanggal**: tanggal kiriman itu berubah dan riwayat perubahannya tercatat. Untuk menunjukkan pengawasan, lihat juga lonceng "Stok disamakan": pemberitahuannya hilang setelah Supervisor mengecek fisik kiriman itu.
7. Login lagi sebagai **rinastaff@gmail.com** (Rina, Staff lain), buka pengajuan yang disetujui, klik **Tandai Selesai**. Stok keluar tercatat **otomatis** (lihat Keluar-Masuk Stok, keterangan "Dari pengajuan").
8. Login **budiadmin@gmail.com** (Budi, Admin): kelola Pengguna (tambah akun baru, nonaktifkan, reset password; lalu tunjukkan bahwa akun baru **wajib membuat password sendiri** saat pertama masuk) dan Data Produk; buka **Laporan**, pilih laporan, lalu **Unduh Excel**; buka **Riwayat Aktivitas**.
9. Tunjukkan pembatasan: Admin tidak bisa mencatat stok atau menyetujui; Staff tidak bisa membuka Laporan; **tonostaff@gmail.com** (Tono, akun nonaktif) tidak bisa login; salah password 5 kali membuat akun dikunci 15 menit.
10. Di **Data Produk** (sebagai Supervisor/Admin) atau **Stok Barang** (sebagai Staff), coba **Impor File** (klik **Unduh Contoh File** dulu), termasuk file yang salah untuk menunjukkan bahwa tidak ada data yang tersimpan.

---

## F. Untuk dosen / penguji

- Dokumen: folder `SD/` (System Design dan SRS versi 2.1).
- Cara kerja, alat yang dipakai, dan letak ketentuan dosen dijelaskan di bagian **G**.
- Menjalankan tes otomatis (setelah masuk venv): `py -m pytest -q`. Tes memakai database tiruan, jadi tidak butuh koneksi Atlas.
- Struktur kode: `app/modules/<fitur>/{routes.py, services.py}` (route tipis, logika di service), `app/common/` (keamanan, validasi, audit, penomoran), `app/templates` dan `public/static` (tampilan Webix).

---

## G. Cara kerja aplikasi (penjelasan sederhana, untuk dijelaskan ke pengguna dan dosen)


### G1. Aplikasi ini untuk apa? (versi satu paragraf)

Bayangkan **satu minimarket** dengan banyak barang yang punya **tanggal kedaluwarsa**. Barang yang sama bisa datang beberapa kali dengan tanggal kedaluwarsa berbeda; satu kali kedatangan disebut **batch**. Aplikasi ini adalah **buku catatan pintar**: mencatat stok tiap batch, **menghitung sendiri** mana yang hampir atau sudah kedaluwarsa, **memberi saran** apa yang sebaiknya dilakukan, dan mengatur **izin**: barang kedaluwarsa atau rusak hanya boleh diretur/dimusnahkan setelah disetujui Supervisor. Aplikasi ini **bukan kasir**; barang terjual dicatat Staff sebagai rekap per produk (misalnya harian).

### G2. Siapa yang memakai? (3 peran)

| Peran | Boleh apa (singkat) |
|---|---|
| **Staff** | Mencatat stok masuk/keluar, memeriksa fisik, menyesuaikan stok dari hasil pemeriksaan, mengajukan retur/pemusnahan, menandai selesai. |
| **Supervisor** | Mengelola produk, **menyetujui/menolak** pengajuan dan koreksi tanggal, memeriksa fisik (cek silang), melihat laporan dan riwayat aktivitas. Tidak mencatat stok. |
| **Admin** | Admin **sistem**: mengelola akun dan produk, melihat semua data, laporan, dan riwayat aktivitas, memantau penyesuaian stok. Tidak menjalankan operasional stok dan tidak menyetujui. |

Prinsipnya **pemisahan tugas**: yang mencatat (Staff) berbeda dengan yang menyetujui (Supervisor), dan yang mengurus akun (Admin) tidak ikut menyetujui; kalau boleh, Admin bisa membuat akun palsu lalu menyetujui pengajuannya sendiri. Aturan ini dijaga di **server**, bukan hanya disembunyikan di tampilan.

### G3. Alur kerja di aplikasi (urut dari awal sampai akhir)

1. **Admin menyiapkan** akun dan master produk.
2. **Barang datang**: Staff mencatat stok masuk. Sistem membuat **batch baru** dengan nomor otomatis dan mencatat "stok masuk".
3. **Status kedaluwarsa dihitung otomatis** setiap halaman dibuka: **Normal** (lebih dari 30 hari), **Monitoring** (15–30), **Near Expired** (8–14), **Critical** (1–7), **Expired** (0 hari atau lewat). Pada tanggal kedaluwarsanya, barang sudah Expired dan tidak boleh dijual.
4. **Barang terjual**: Staff mencatat total terjual per produk (misalnya dari rekap kasir). Sistem mengurangi stok dari batch yang paling cepat kedaluwarsa (**FEFO** = *First Expired, First Out*). Barang Expired atau rusak tidak ikut terjual. Bila stok sama atau di bawah **stok minimum**, produk masuk daftar **stok menipis**.
5. **Pemeriksaan fisik**: petugas menghitung barang, mengecek kondisinya (berapa yang rusak), dan mencocokkan tanggal di kemasan. Pemeriksaan tidak mengubah stok. Kalau jumlahnya berbeda, Staff menekan **"Samakan stok"** (tanpa izin, tetapi Supervisor dan Admin diberi tahu). Kalau tanggal di kemasan berbeda, Supervisor yang memutuskan koreksinya.
6. **Saran Tindakan**: aplikasi memberi saran dari **aturan sederhana** (bukan AI), misalnya Expired → ambil dari rak dan ajukan retur/pemusnahan; kemasan rusak → pisahkan. Setiap saran ada alasannya. Rekomendasi tidak mengubah apa pun.
7. **Pengajuan (perlu izin)**:
   - Staff **mengajukan** retur atau pemusnahan (status *Menunggu*).
   - Supervisor **menyetujui** (*Disetujui*) atau **menolak** (*Ditolak*, alasan wajib).
   - Barang **ditangani di luar aplikasi** (dibuang atau dikembalikan ke pemasok).
   - Staff mana pun menandai **Selesai**, mengisi jumlah yang benar-benar ditangani, dan **keterangan bukti** (retur: ke pemasok mana dan nomor dokumennya; pemusnahan: caranya dan siapa saksinya), seperti berita acara sederhana. Sistem **otomatis mencatat stok keluar**.
   - **Kenapa pemusnahan jadi pilihan terakhir?** Di ritel, barang yang dibuang adalah kerugian toko. Jadi urutannya: **jual dulu** (FEFO) → kalau tidak akan laku, **retur ke pemasok** selagi masih layak (kerugian bisa ditanggung pemasok sesuai perjanjian) → **musnahkan** hanya barang yang sudah Expired atau rusak. Aplikasi ini membantu menekan pemusnahan lewat peringatan sejak 30 hari sebelum kedaluwarsa.
   - Kalau tidak jadi, pengajuan bisa **Dibatalkan**.
   - Semua langkah tercatat di **riwayat** (siapa, kapan, catatannya).
8. **Laporan dan riwayat aktivitas**: Supervisor dan Admin melihat 9 laporan, mengekspornya ke Excel, dan melihat siapa melakukan apa.

### G4. Alat apa saja yang dipakai? (tools)

**Tampilan (frontend), yang dilihat pengguna di browser**
- **Webix** (komponen tampilan siap pakai: tabel, form, menu, jendela). Ini satu-satunya "framework" tampilan; **tidak ada** React, Vue, atau Bootstrap.
- **HTML + CSS + JavaScript biasa**. CSS buatan sendiri ada di `public/static/css/app.css`; file Webix disimpan lokal di `public/static/vendor/webix` (tidak perlu internet untuk memuatnya).
- Di **laptop** data ditampilkan sebagai **tabel**; di **HP** sebagai **kartu** (satu kartu per baris) dan menu menjadi laci.

**Server (backend), otak aplikasinya**
- **Python + Flask**: menerima permintaan dari browser dan memberi jawaban.
- **Flask-WTF**: perlindungan **CSRF** (mencegah halaman palsu mengirim perintah atas nama pengguna yang sedang login).
- **Werkzeug**: menyimpan password dalam bentuk **hash** (diacak satu arah).
- **python-dotenv**: membaca file `.env` (kunci rahasia dan alamat database), supaya rahasia tidak ditulis di kode.
- **dnspython**: dibutuhkan pymongo supaya alamat Atlas `mongodb+srv://` bisa dipakai.
- **Penulis file Excel buatan sendiri** (`app/common/xlsx.py`): memakai modul `zipfile` bawaan Python, jadi tidak butuh paket tambahan.

**Database**
- **MongoDB Atlas** (database di internet, tipe dokumen), lewat **pymongo**.
- **7 koleksi** (mirip tabel): `master_karyawan` (akun dan peran), `master_product` (produk), `batches`, `stock_movements`, `inspections`, `handling_requests`, `audit_logs`. Tidak ada koleksi lokasi (satu outlet), notifikasi, atau pengaturan.

**Pengujian**
- **pytest** dan **mongomock** (database tiruan di memori): 265 tes otomatis tanpa koneksi Atlas.

### G5. Bagaimana tampilan dan server "ngobrol"?

1. **Browser** (Webix) mengirim permintaan ke alamat seperti `/api/v1/batches` (format data: JSON).
2. **Flask** menerima. Pertama dicek: *sudah login? perannya boleh?*
3. **Logika bisnis** (`services.py`) memeriksa isi data lalu menjalankan aturan (misalnya "stok keluar tidak boleh melebihi stok" atau "batch Expired tidak boleh dijual").
4. **pymongo** membaca atau menulis ke **MongoDB Atlas**. Perubahan stok dan catatannya disimpan bersama dalam satu **transaksi**, jadi tidak ada yang tersimpan setengah.
5. Server mengirim jawaban JSON; **Webix** menampilkannya. Semua teks dari server di-*escape* (supaya tidak bisa menyisipkan kode jahat).

| Lokasi | Isinya |
|---|---|
| `main.py` | Pintu masuk; dijalankan dengan `py main.py` |
| `seed.py` | Mengisi data contoh (dijalankan manual) |
| `app/modules/<fitur>/routes.py` | "Pintu" tiap fitur: menerima permintaan, tipis saja |
| `app/modules/<fitur>/services.py` | Aturan dan logika fitur (inti pekerjaan) |
| `app/modules/movements/ledger.py` | Satu-satunya tempat stok batch diubah |
| `app/common/` | Alat bersama: cek login/peran, validasi, audit, tanggal, penomoran |
| `app/indexes.py` | Daftar indeks database |
| `app/templates/`, `public/static/js/` | Halaman HTML dan kode tampilan per halaman (Webix) |
| `tests/` | Tes otomatis |
| `SD/` | Dokumen System Design dan SRS |

### G6. Ketentuan dosen terletak di mana?

| Ketentuan dosen | Status | Letaknya di aplikasi |
|---|---|---|
| **Flask** | Ada | `main.py`, `app/__init__.py`, `app/modules/*/routes.py` |
| **MongoDB** | Ada | `app/db.py` (koneksi), 7 koleksi di Atlas, dipakai lewat pymongo di setiap `services.py` |
| **Deploy aplikasi** | **Belum** (menunggu konfirmasi dosen) | Saat ini berjalan di komputer sendiri (`py main.py`). Jangan klaim sudah ter-deploy |
| **Authentication** (login) | Ada | `app/modules/auth` + `login.html`. Password di-hash, akun nonaktif ditolak, sesi habis setelah 8 jam, akun dikunci 15 menit setelah 5 kali salah password |
| **Authorization** (hak akses) | Ada | `app/common/permissions.py` + pemeriksaan di setiap route. Tiga peran dengan tugas berbeda; contoh: pengajuan hanya disetujui Supervisor, Admin tidak bisa mencatat stok |
| **Validasi dan sanitasi** | Ada | `app/common/http.py`, `app/common/dates.py`: wajib diisi, tipe, panjang, tanggal, jumlah tidak negatif, teks dengan `<` `>` ditolak, awalan `=` `+` `@` (dan `-` tanpa spasi) ditolak. Ditambah CSRF, escape di tampilan, dan impor CSV yang ketat |
| **Simulasi multi user dan multi role** | Ada | `seed.py`: 1 Admin, 2 Supervisor, 3 Staff, 1 akun nonaktif. Skenario di bagian **E** |
| **Technical documentation** | Ada | Folder `SD/` (SRS dan System Design versi 2.1) dan README ini |
| **FE Webix** (opsional) | Ada | `public/static/js/*.js` dan `public/static/vendor/webix` |
| **UI responsive** (opsional) | Ada | Laptop: sidebar + tabel. HP: menu laci + kartu per baris (ukuran dipilih saat halaman dibuka) |
| **Indexing MongoDB** (opsional) | Ada | `app/indexes.py`: indeks **teks** (cari produk), **majemuk** (FEFO, monitoring, riwayat), dan **unik** (email, SKU, nomor batch, nomor pengajuan, serta pencegah transaksi ganda) |
| **Unit testing** (opsional) | Ada | Folder `tests/`, dijalankan dengan `py -m pytest -q` (265 tes) |

### G7. Beberapa istilah yang mungkin ditanyakan

- **Batch**: satu kali kedatangan barang dengan satu tanggal kedaluwarsa.
- **FEFO**: yang paling cepat kedaluwarsa dijual atau dikeluarkan lebih dulu.
- **Layak / sebagian rusak / tidak layak**: dari cek fisik terakhir. *Sebagian rusak*: ada barang rusak yang dipisahkan, sisanya tetap dijual. *Tidak layak*: semua sisa barang rusak, atau batch sudah Expired.
- **Stok minimum**: batas untuk pesan ulang; kalau stok yang bisa dijual sama atau di bawahnya, produk masuk daftar stok menipis.
- **Penyesuaian stok**: membetulkan angka stok di sistem supaya sama dengan hasil hitung fisik.
- **Pengajuan**: permintaan izin retur/pemusnahan ke Supervisor.
- **Seed**: mengisi database dengan data contoh.
- **Hash password**: password diacak satu arah; yang disimpan hanya hasil acakannya.
- **CSRF**: serangan yang menipu browser pengguna agar mengirim perintah tanpa disadari; dicegah dengan token rahasia.
- **Transaksi database**: beberapa perubahan disimpan bersama-sama atau dibatalkan semuanya.
- **Indeks (index)**: "daftar isi" di database supaya pencarian cepat dan data tetap unik.
- **Audit log / riwayat aktivitas**: catatan siapa melakukan apa dan kapan.

### G8. Hal yang perlu jujur disampaikan saat presentasi

- Aplikasi **belum online (deploy)**; berjalan di komputer sendiri.
- Rekomendasi memakai **aturan sederhana**, **bukan AI**; hanya saran, keputusan tetap di manusia.
- Aplikasi **bukan kasir (POS)**; barang terjual dicatat sebagai rekap (per produk, misalnya harian), jadi angka stok adalah stok **tercatat**. Selisih dengan kenyataan ditemukan lewat cek fisik.
- Tes otomatis memakai database tiruan; koneksi, transaksi, dan indeks di **MongoDB Atlas asli** sudah dicoba (14 Nov 2026).
- Daftar yang belum ada atau sengaja tidak dibuat ada di bagian **D**.

---

## H. File dan folder yang TIDAK boleh ikut dikirim atau di-upload (diatur di `.gitignore`)

Daftar ini ditulis di file `.gitignore` supaya Git (dan GitHub) mengabaikannya. Kalau folder project dikirim sebagai ZIP, **keluarkan juga** hal-hal ini secara manual.

| Jangan ikut | Alasannya |
|---|---|
| `.env` | Berisi kunci rahasia dan alamat database (berisi password). Yang boleh ikut hanya `.env.example` (kosong). |
| `venv/` | Terikat ke komputer pembuatnya. Dibuat ulang di komputer baru (bagian A1 dan A3). |
| `__pycache__/`, `.pytest_cache/` | File sementara buatan Python/pytest. |
| `*.xlsx`, `*.xls`, `~$*` | Hasil ekspor Excel yang tersimpan di folder project berisi data usaha; `~$` adalah file kunci sementara milik Excel. |
| `*.pem`, `*.key`, `*.p12` | Sertifikat dan kunci pribadi. |
| `*.zip`, `*.log` | Paket kirim lama dan catatan log. |
| `.vscode/`, `.idea/`, `*.code-workspace` | Pengaturan editor pribadi. |

Yang **harus ikut**: folder `app/` dan `public/` (termasuk `public/static/vendor/webix`, karena tampilan memakai file ini tanpa internet), `tests/`, `SD/` (SD dan SRS), `main.py`, `seed.py`, `requirements.txt`, `pytest.ini`, `README.md`, `.env.example`, dan `.gitignore`.


---

## I. Deploy ke Vercel (aplikasi online)

Aplikasi sudah disiapkan untuk Vercel: `index.py` (titik masuk), `vercel.json` (pengaturan fungsi), `.python-version` (Python 3.14), dan file tampilan ada di `public/static` (Vercel hanya melayani file statis dari folder `public/`). Menjalankan di komputer sendiri tetap `py main.py`.

**Yang perlu dipahami dulu**
- Vercel menjalankan aplikasi sebagai fungsi *serverless*: tidak ada server yang selalu menyala, jadi permintaan pertama setelah lama sepi bisa terasa lambat beberapa detik. Itu wajar.
- Aplikasi online memakai **database Atlas yang sama** dengan yang di komputermu. Data yang diubah di sana terlihat di sini, dan sebaliknya.
- Nilai rahasia (`SECRET_KEY`, `MONGO_URI`) **hanya diisi di dashboard Vercel**, tidak pernah ditulis di file yang ikut di-upload.

**Langkah 1. Izinkan Vercel mengakses Atlas**
1. Buka MongoDB Atlas, menu **Network Access**, klik **Add IP Address**.
2. Pilih **Allow Access From Anywhere** (`0.0.0.0/0`), lalu **Confirm**.
3. Alasannya: alamat IP Vercel berubah-ubah, jadi tidak bisa didaftarkan satu per satu. Artinya keamanan database bertumpu pada **password user database**. Pastikan password itu kuat, dan di menu **Database Access** user itu hanya diberi hak `readWrite` pada database `smart_expiry_db` (jangan "Atlas admin").
4. Catat **region** cluster-mu (di halaman cluster, contoh: *AWS / Singapore*). Dipakai di Langkah 4.

**Langkah 2. Periksa sebelum mengunggah ke GitHub (kamu sendiri)**
- Folder `public/` **harus ikut** (isi tampilannya). File `.env`, folder `venv/`, dan file catatan pribadi lain di komputermu **tidak boleh ikut** (sudah diatur di `.gitignore`).
- Sebelum commit, jalankan `git status` dan pastikan `.env` tidak muncul di daftar file yang akan masuk.
- Commit memakai identitas Git-mu sendiri (`git config user.name` dan `git config user.email`).

**Langkah 3. Buat project di Vercel**
1. Masuk ke vercel.com dengan akun GitHub-mu, klik **Add New > Project**, lalu pilih repository aplikasi ini.
2. **Framework Preset** biasanya terdeteksi sebagai *Flask*. **Root Directory** biarkan `./`. Build Command dan Output Directory dibiarkan kosong.
3. Sebelum menekan Deploy, buka **Environment Variables** dan isi (untuk Production):

| Nama | Isi |
|---|---|
| `SECRET_KEY` | Teks acak panjang. Buat dengan `py -c "import secrets; print(secrets.token_hex(32))"`. Boleh berbeda dari yang di `.env` lokal. |
| `MONGO_URI` | Salin dari file `.env`-mu sendiri (alamat koneksi Atlas). **Jangan dibagikan ke siapa pun.** |
| `DATABASE_NAME` | `smart_expiry_db` |
| `FLASK_ENV` | `production` |

`SESSION_COOKIE_SECURE` tidak perlu diisi: di Vercel otomatis aktif.
4. Klik **Deploy**, tunggu sampai selesai, lalu buka alamat `https://nama-project.vercel.app`.

**Langkah 4. Samakan region dengan Atlas (supaya cepat)**
Vercel secara bawaan menjalankan fungsi di Amerika Serikat (`iad1`). Bila Atlas-mu di Singapura, aplikasi akan terasa lambat. Buka project di Vercel, **Settings > Functions > Function Region**, pilih region yang terdekat dengan Atlas (untuk Singapura: *Singapore (sin1)*), lalu **Redeploy** dari tab Deployments.

**Langkah 5. Uji setelah online**
1. Halaman login tampil rapi (ada warna dan huruf, bukan teks polos).
2. Login sebagai Staff, Supervisor, dan Admin, lalu buka semua menu.
3. Catat satu barang terjual, lalu lihat apakah muncul di Keluar-Masuk Stok.
4. Jangan sengaja salah password 5 kali pada akun demo (akunnya terkunci 15 menit).

**Bila ada masalah**

| Gejala | Kemungkinan penyebab | Perbaikan |
|---|---|---|
| Tampilan polos tanpa warna, atau file `/static/...` tidak ketemu | Folder `public/` belum ikut ke GitHub | Pastikan `public/static` ada di repository, lalu push ulang |
| Tulisan "pengaturan ... belum diisi" | Environment Variables belum diisi atau belum Redeploy | Isi di Settings > Environment Variables, lalu Redeploy (perubahan tidak berlaku ke deployment lama) |
| "Ada masalah di aplikasi" atau lama sekali lalu gagal | Atlas belum mengizinkan `0.0.0.0/0`, atau `MONGO_URI` salah | Ulangi Langkah 1 dan periksa `MONGO_URI` |
| Login selalu ditolak | Database yang dipakai berbeda atau akun belum ada | Periksa `DATABASE_NAME` dan koleksi `master_karyawan` di Atlas |
| Build gagal | Lihat pesan di tab Deployments > Build Logs | Salin pesannya untuk diperiksa |

Log aplikasi yang sedang berjalan ada di Vercel, menu **Logs**.
