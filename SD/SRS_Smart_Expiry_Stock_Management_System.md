# SOFTWARE REQUIREMENTS SPECIFICATION (SRS)
## Sistem Monitoring Stok dan Kedaluwarsa Produk pada Satu Outlet

| | |
|---|---|
| Versi | **2.1** |
| Tanggal | 14 November 2026 |
| Dokumen terkait | `SD_Smart_Expiry_Stock_Management_System.md` versi 2.1 (rincian aturan, database, dan arsitektur) |

**Padanan istilah.** Di layar, pesan, dan laporan, istilah teknis di dokumen ini tampil dalam bahasa sehari-hari yang baku (misalnya Batch = *Kiriman*, Monitoring = *Perlu Dipantau*, Critical = *Kritis*, Retur = *Pengembalian*). Tabel lengkapnya ada di SD, bagian pembuka (Padanan istilah).

**Riwayat perubahan**

| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.1–1.2 | 10–11 Nov 2026 | Kebutuhan versi multi-outlet. |
| 2.0 | 12 Nov 2026 | Diselaraskan dengan SD 2.0: satu outlet, peran baru, batas status tetap, penyesuaian langsung oleh Staff dari hasil pemeriksaan, pengajuan dua jenis (retur, pemusnahan) dan lima status, tanpa diskon, stok keluar = terjual, delapan laporan. |
| 2.1 | 14 Nov 2026 | Praktik ritel (SD 15, keputusan 16–23): stok minimum + laporan stok menipis; barang terjual per produk (FEFO otomatis) + impor rekap penjualan; barang rusak per buah; koreksi tanggal kedaluwarsa lewat cek fisik + persetujuan Supervisor; penyesuaian tampil di pemberitahuan Supervisor/Admin; kunci login 15 menit setelah 5 kali salah; Admin = admin sistem; barang rusak saat datang ditolak di penerimaan; satuan besar saat barang datang; jadwal cek fisik; ganti password sendiri (wajib setelah dibuat/direset Admin); keluar otomatis 30 menit tanpa aktivitas; tanggal penjualan; pengajuan tidak bertumpuk. |

SRS menjelaskan **apa** yang harus dilakukan sistem. **Bagaimana** caranya dijelaskan di SD. Bila ada perbedaan, SD 2.1 yang berlaku.

---

# 1. PENDAHULUAN

## 1.1 Ruang lingkup

Aplikasi web untuk **satu outlet**: mencatat produk, stok masuk/keluar per batch, memantau kedaluwarsa per batch, mencatat pemeriksaan fisik, memberi rekomendasi berbasis aturan, serta mencatat pengajuan dan persetujuan tindak lanjut, lengkap dengan laporan dan riwayat.

**Bukan** POS, ERP, atau sistem multi-outlet. Tidak ada integrasi sistem lain, AI, bundling, transfer stok, pembelian/supplier, atau notifikasi WhatsApp/SMS/email (SD bagian 3).

## 1.2 Istilah

| Istilah | Arti |
|---|---|
| Batch | Satu kali penerimaan barang; memiliki satu tanggal kedaluwarsa dan nomor batch internal dari sistem. |
| FEFO | First Expired, First Out: yang paling cepat kedaluwarsa dikeluarkan lebih dulu. |
| Pergerakan stok | Catatan stok masuk, stok keluar, atau penyesuaian. Satu-satunya cara stok berubah. |
| Layak | Batch belum Expired dan tidak ada barang rusak yang belum ditangani. *Sebagian rusak*: sebagian barang rusak (dipisahkan), sisanya tetap boleh dijual. |
| Stok yang boleh dijual | Stok batch yang belum Expired dikurangi barang rusak yang belum ditangani. |
| Stok minimum | Titik pesan ulang per produk; stok yang boleh dijual ≤ angka ini = stok menipis. |
| Pengajuan | Permintaan penanganan barang kedaluwarsa, mendekati kedaluwarsa, atau rusak (retur, pemusnahan) dari Staff yang perlu persetujuan Supervisor sebelum stok diubah. |
| Penyesuaian stok | Perbaikan stok sistem agar sama dengan hasil pemeriksaan fisik; dicatat langsung oleh Staff tanpa persetujuan. |
| Stok keluar | Pencatatan barang yang **terjual**, per produk (rekap); batch dipilih otomatis FEFO. Barang yang keluar karena alasan lain melalui pengajuan. |

## 1.3 Pemetaan ke ketentuan dosen

| Ketentuan | Jenis | Dipenuhi oleh |
|---|---|---|
| Flask | Wajib | Backend (SD 10) |
| MongoDB | Wajib | MongoDB Atlas, 7 koleksi (SD 8) |
| Deploy aplikasi | Wajib, menunggu konfirmasi dosen | SD 14 risiko 10 |
| Authentication | Wajib | FR-AUTH, SD 11.1 |
| Authorization | Wajib | FR-RBAC, SD 4.2 dan 11.2 |
| Validasi & sanitasi | Wajib | FR-VAL, SD 12 |
| Simulasi multi user dan multi role | Wajib | FR-SEED (3 peran, beberapa akun) |
| Technical documentation | Wajib | SRS ini dan SD |
| FE Webix, UI responsive, indexing MongoDB, unit testing | Opsional | NFR-UI, NFR-DB, NFR-TEST |

---

# 2. PERAN

| Peran | Tugas utama |
|---|---|
| Admin | **Admin sistem** (bukan admin gudang): mengelola akun dan master produk; melihat semua data, laporan, dan riwayat aktivitas; memantau penyesuaian stok. Tidak menjalankan operasional stok dan tidak menyetujui (pemisahan tugas). |
| Supervisor | Hak master produk sama dengan Admin; menyetujui/menolak pengajuan dan usulan koreksi tanggal kedaluwarsa; pemeriksaan fisik; memantau aktivitas, penyesuaian, dan stok menipis. Tidak bersinggungan langsung dengan data gudang (tidak mencatat atau mengoreksi stok dan batch). |
| Staff | Mencatat stok masuk/keluar; pemeriksaan fisik; penyesuaian stok dari hasil pemeriksaan; mengajukan retur/pemusnahan; mencatat penyelesaian. |

Matriks hak akses lengkap: SD 4.2.

---

# 3. KEBUTUHAN FUNGSIONAL

## 3.1 Autentikasi (FR-AUTH)
- FR-AUTH-01: Login dengan email dan password; password disimpan sebagai hash.
- FR-AUTH-02: Akun nonaktif tidak dapat login; penonaktifan berlaku pada permintaan berikutnya.
- FR-AUTH-03: Pesan login gagal bersifat umum.
- FR-AUTH-04: Sesi berbasis cookie; berakhir 8 jam setelah login atau saat logout. Logout membuat salinan cookie lama tidak berlaku (versi sesi naik).
- FR-AUTH-06: Sesi berakhir bila tidak ada aktivitas pengguna selama 30 menit; pengecekan otomatis (lonceng) tidak dihitung sebagai aktivitas.
- FR-AUTH-07: Pengguna dapat mengganti password sendiri (password lama wajib). Akun baru dan akun yang direset Admin wajib membuat password sendiri sebelum memakai aplikasi.
- FR-AUTH-05: Setelah 5 kali salah password berturut-turut, akun dikunci 15 menit (password benar pun ditolak); login berhasil mengembalikan hitungan; Admin dapat membuka kunci dengan mengatur ulang password; kejadian tercatat di audit log.

## 3.2 Otorisasi (FR-RBAC)
- FR-RBAC-01: Setiap endpoint memeriksa peran di server sesuai SD 4.2.
- FR-RBAC-02: Pengajuan hanya dibuat oleh Staff dan hanya diputuskan oleh Supervisor; peninjau tidak boleh sama dengan pengaju.
- FR-RBAC-03: Peran dan izin ditetapkan di kode. Admin mengatur peran tiap akun, status aktif, dan password baru.
- FR-RBAC-04: Admin tidak dapat menonaktifkan dirinya sendiri atau Admin aktif terakhir.

## 3.3 Pengguna (FR-USR)
- FR-USR-01: Admin menambah, mengubah (nama, peran), mengaktifkan/menonaktifkan akun, dan mengatur ulang password. Email unik dan tidak dapat diubah. Akun tidak dihapus.

## 3.4 Master Produk (FR-PRD)
- FR-PRD-01: Supervisor dan Admin menambah, mengubah, dan menonaktifkan produk; Staff hanya melihat. SKU unik dan tidak dapat diubah. Data produk: SKU, nama, kategori, satuan, harga jual (rupiah, informasi saja), stok minimum (≥ 0, 0 = tidak dipantau), satuan besar + isinya (opsional), deskripsi, status.
- FR-PRD-02: Produk yang sudah memiliki batch tidak dapat dihapus permanen.
- FR-PRD-03: Pencarian SKU/nama; filter kategori dan status.
- FR-PRD-04: Impor CSV produk (Supervisor, Admin).

## 3.5 Manajemen Stok (FR-STK)
- FR-STK-01: Staff mencatat stok masuk (produk aktif, jumlah, tanggal masuk, tanggal kedaluwarsa). Setiap penerimaan membuat batch baru dengan nomor internal dari sistem dan satu `stock_in` dalam satu transaksi.
- FR-STK-01a: Bila produk punya satuan besar, jumlah datang boleh diisi dalam satuan besar + satuan kecil; sistem mengubahnya ke satuan terkecil. Stok selalu dalam satuan terkecil.
- FR-STK-01b: Barang rusak saat datang dicatat sebagai **jumlah ditolak** (alasan wajib) dan tidak masuk stok; bila semua ditolak, tidak ada batch tetapi kejadiannya tercatat di audit log.
- FR-STK-02: Tanggal masuk ≤ hari ini; tanggal kedaluwarsa > tanggal masuk dan > hari ini. Sebelum disimpan, sistem menampilkan layar konfirmasi berisi sisa hari dan status. Data batch tidak dapat diubah langsung; tanggal kedaluwarsa hanya dapat dikoreksi lewat FR-INS-04.
- FR-STK-03: Staff mencatat barang terjual **per produk** (rekap, misalnya harian) **tanpa alasan**; sistem otomatis mengurangi stok dari batch yang boleh dijual, urut FEFO, berlanjut ke batch berikutnya bila perlu, dalam satu transaksi. Staff juga dapat mengimpor file rekap penjualan (`sku,quantity,sale_date`). Tanggal penjualan default hari ini, boleh mundur paling lama 7 hari, tidak boleh di masa depan; batch yang datang setelah tanggal itu tidak ikut dikurangi.
- FR-STK-04: Stok keluar tidak boleh melebihi stok yang boleh dijual; stok tidak pernah negatif.
- FR-STK-05: Stok keluar biasa tidak pernah mengambil barang Expired atau barang rusak yang belum ditangani.
- FR-STK-06: Staff mencatat penyesuaian stok **langsung tanpa persetujuan** (tetapi selalu tampil di pemberitahuan Supervisor dan Admin selama 7 hari), tetapi hanya dari hasil pemeriksaan yang memiliki selisih: arah dan jumlah otomatis dari selisih, satu penyesuaian per pemeriksaan, dan ditolak bila stok batch sudah berubah sejak pemeriksaan.
- FR-STK-07: Pergerakan stok tidak dapat diubah atau dihapus; setiap pergerakan memiliki sumber (`manual`, `csv_import`, `inspection`, `handling_request`), pencatat, serta jumlah sebelum dan sesudah.
- FR-STK-08: Kiriman ganda dicegah (`client_request_id` unik).

## 3.6 Monitoring Kedaluwarsa (FR-EXP)
- FR-EXP-01: Sisa hari = tanggal kedaluwarsa − hari ini (WIB).
- FR-EXP-02: Status dihitung saat dibaca, tidak disimpan: Normal (> 90), Monitoring (31–90), Critical (1–30), Expired (≤ 0). Barang tidak boleh dijual pada tanggal kedaluwarsanya; sisa 0 hari diberi label "Kedaluwarsa hari ini".
- FR-EXP-03: Batas hari ditetapkan di kode.
- FR-EXP-04: Daftar monitoring menampilkan batch Monitoring sampai Expired dengan stok > 0, diurutkan dari yang paling dekat kedaluwarsa.
- FR-EXP-05: Batch dengan stok 0 tidak dipantau; batch Expired tidak dihapus otomatis.

## 3.7 Pemeriksaan Fisik (FR-INS)
- FR-INS-01: Staff dan Supervisor mencatat jumlah fisik (semua barang, termasuk yang rusak), kondisi produk (`baik`/`rusak`), kondisi kemasan (`baik`/`rusak`), **jumlah yang rusak** (wajib bila ada yang rusak), kecocokan **tanggal di kemasan**, dan catatan. Catatan wajib bila ada selisih, barang rusak, atau tanggal berbeda.
- FR-INS-02: Setiap pemeriksaan adalah catatan baru; riwayat tidak ditimpa.
- FR-INS-03: Pemeriksaan tidak mengubah stok. Bila ada selisih, Staff dapat langsung menyesuaikan stok (FR-STK-06).
- FR-INS-04: Bila tanggal di kemasan berbeda, sistem menyimpan **usulan koreksi**. Supervisor (bukan pemeriksanya) menyetujui atau menolak (alasan wajib). Disetujui → tanggal batch diganti dan tanggal lama disimpan di riwayat batch. Satu usulan menunggu per batch.
- FR-INS-06: Jadwal cek fisik: Critical tiap 3 hari, Monitoring/Normal tiap 14 hari (tanggal datang = cek pertama; Expired tidak dijadwalkan). Batch yang jatuh tempo tampil di daftar "Perlu dicek", dashboard Staff, dan lonceng Staff.
- FR-INS-05: Barang rusak dihitung per buah: stok yang boleh dijual = stok − barang rusak yang belum ditangani; barang rusak berkurang saat pengajuan barang rusak diselesaikan.

## 3.8 Rekomendasi (FR-REC)
- FR-REC-01: Rekomendasi dihitung saat dibuka, satu per batch, menurut urutan aturan di SD 5.5 B (Expired → rusak → Critical → Monitoring → Normal).
- FR-REC-02: Setiap rekomendasi menampilkan alasannya.
- FR-REC-03: Tidak ada rekomendasi diskon. Batch Expired atau tidak layak selalu mendapat rekomendasi tarik/pisahkan dan ajukan retur atau pemusnahan.
- FR-REC-04: Rekomendasi tidak mengubah stok dan tidak menjalankan tindakan.

## 3.9 Pengajuan Tindak Lanjut (FR-REQ)
- FR-REQ-01: Pengajuan dipakai untuk penanganan barang kedaluwarsa, mendekati kedaluwarsa, atau rusak. Jenis: Retur, Pemusnahan. Setiap pengajuan punya **dasar**: Barang Expired, Barang rusak, atau Mendekati kedaluwarsa (Critical). Batch Normal/Monitoring tanpa barang rusak tidak boleh diajukan.
- FR-REQ-01a: Barang Expired wajib diajukan **seluruh stok batch**; barang rusak wajib diajukan **semua barang rusak itu** (jumlah dari cek fisik); barang mendekati kedaluwarsa yang masih bagus boleh sebagian. Pengajuan tidak mengunci stok.
- FR-REQ-01b: **Pemusnahan hanya untuk barang Expired atau rusak**; barang yang masih bagus hanya boleh diretur (urutan jual → retur → musnahkan).
- FR-REQ-01c: Staff dapat melaporkan **barang rusak langsung** di form Ajukan untuk batch yang belum Expired, tanpa Cek Fisik. Jumlah (paling banyak stok yang belum ditahan) **ditahan**: tidak bisa dijual selama pengajuan Menunggu atau Disetujui; dilepas bila Ditolak atau Dibatalkan; menjadi pengurangan stok bila Selesai. Bila batch sudah punya rusak tercatat lewat Cek Fisik, yang diajukan adalah jumlah tercatat itu. Dropdown produk di form Ajukan memuat semua produk berstok, dengan keterangan alasan bagi yang perlu ditangani.
- FR-REQ-02: Status: Menunggu → Disetujui / Ditolak / Dibatalkan; Disetujui → Selesai / Dibatalkan. Status akhir tidak dapat diubah.
- FR-REQ-03: Alasan wajib saat mengajukan, saat menolak, dan saat Supervisor membatalkan.
- FR-REQ-04: Hanya satu pengajuan terbuka per batch dan dasar; pengajuan Barang Expired ditolak selama masih ada pengajuan lain yang terbuka untuk batch itu.
- FR-REQ-05: Staff mana pun dapat mencatat penyelesaian beserta jumlah yang ditangani dan **keterangan bukti wajib** (retur: pemasok dan nomor dokumen; pemusnahan: cara dan saksi). Saat Selesai, sistem otomatis mencatat `stock_out` dalam transaksi yang sama.
- FR-REQ-06: Satu pengajuan menghasilkan paling banyak satu pergerakan stok.
- FR-REQ-07: Jumlah yang ditangani saat Selesai tidak boleh melebihi jumlah yang disetujui maupun stok batch saat itu.
- FR-REQ-08: Setiap langkah tercatat di riwayat pengajuan (aksi, pelaku, peran, waktu, catatan).

## 3.10 Dashboard dan Notifikasi (FR-DSH)
- FR-DSH-01: Kartu: total produk aktif, total stok yang boleh dijual, jumlah batch per status (stok > 0), pengajuan menunggu persetujuan, stok menipis, dan barang rusak. Staff juga melihat pengajuan Disetujui yang belum selesai; Supervisor dan Admin melihat jumlah penyesuaian 7 hari terakhir yang belum dicek ulang Supervisor; Supervisor melihat usulan koreksi tanggal yang menunggu.
- FR-DSH-02: Lonceng notifikasi dihitung saat dibuka: Supervisor melihat pengajuan Menunggu, usulan koreksi tanggal, dan penyesuaian 7 hari yang belum dicek ulang (hilang setelah Supervisor mengecek fisik kiriman itu); Admin melihat penyesuaian yang belum dicek ulang; stok menipis tidak masuk lonceng; Staff melihat pengajuan Disetujui dan pengajuan miliknya yang Ditolak dalam 7 hari.

## 3.11 Laporan dan Riwayat (FR-RPT)
- FR-RPT-01: Sembilan laporan (Supervisor, Admin): stok produk, stok menipis, stok per batch, mendekati kedaluwarsa, kedaluwarsa, riwayat stok masuk/keluar, riwayat penyesuaian, riwayat pemeriksaan, riwayat pengajuan.
- FR-RPT-02: Ekspor `.xlsx` berisi semua baris sesuai filter, maksimal 20.000 baris (lebih dari itu ditolak); teks tidak pernah ditulis sebagai rumus; setiap ekspor tercatat.
- FR-RPT-03: Halaman Riwayat Aktivitas (Supervisor, Admin) menampilkan audit log; hanya dapat dibaca.

## 3.12 Impor CSV (FR-CSV)
- FR-CSV-01: Template dapat diunduh untuk produk, stok awal, dan rekap penjualan harian.
- FR-CSV-02: Alur: unggah → validasi semua baris → pratinjau dengan error per baris → konfirmasi → simpan dalam satu transaksi.
- FR-CSV-03: Mode strict: satu baris salah berarti tidak ada yang disimpan.
- FR-CSV-04: Validasi sesuai SD 9.4 (header, tipe, tanggal, SKU tidak ditemukan, duplikat, jumlah).
- FR-CSV-05: File stok awal atau rekap penjualan yang sama tidak dapat diimpor dua kali.
- FR-CSV-06: Input manual lewat form tetap tersedia untuk semua data.

## 3.13 Audit (FR-AUD)
- FR-AUD-01: Login (termasuk akun dikunci), koreksi tanggal kedaluwarsa, perubahan pengguna/produk, stok masuk/keluar, pemeriksaan, setiap langkah pengajuan, impor, dan ekspor dicatat di audit log.
- FR-AUD-02: Audit log tidak dapat diubah atau dihapus; tidak pernah memuat password atau token.

## 3.14 Validasi (FR-VAL)
- FR-VAL-01: Semua input divalidasi di server (wajib, tipe, panjang, rentang, format tanggal, enum, ObjectId, keberadaan referensi).
- FR-VAL-02: Teks dengan `<`/`>` atau berawalan `=`, `+`, `@`, atau `-` tanpa spasi sesudahnya ditolak; teks di-escape saat ditampilkan.
- FR-VAL-03: Input tidak pernah dipakai sebagai operator query MongoDB; filter dan sortir memakai whitelist.

## 3.15 Seed Data (FR-SEED)
- FR-SEED-01: `seed.py` dijalankan manual dan mengisi data contoh satu outlet: 1 Admin, minimal 1 Supervisor, minimal 3 Staff, 1 akun nonaktif, produk, batch yang mencakup semua status, pergerakan, pemeriksaan (termasuk selisih dan kemasan rusak), dan pengajuan dalam berbagai status.
- FR-SEED-02: Tanggal dibuat relatif terhadap hari dijalankan; aman dijalankan ulang; memberi pesan jelas bila `.env` belum diisi.

---

# 4. KEBUTUHAN NON-FUNGSIONAL

- NFR-SEC-01: Cookie sesi HttpOnly, SameSite=Lax, Secure saat HTTPS; CSRF untuk semua request yang mengubah data.
- NFR-SEC-02: Kredensial hanya di `.env`; pesan error tidak membocorkan detail internal.
- NFR-DATA-01: Pengurangan stok memakai pembaruan bersyarat dan transaksi multi-dokumen; `current_quantity` selalu sama dengan jumlah pergerakan (rekonsiliasi).
- NFR-UI-01: Antarmuka Webix, berbahasa Indonesia, dengan tampilan kosong, loading, sukses, dan error yang jelas.
- NFR-UI-02: Responsif: tabel di desktop tanpa scroll horizontal; kartu per baris di ponsel; menu samping menjadi laci.
- NFR-DB-01: Indeks dibuat otomatis saat aplikasi mulai: unik (email, SKU, nomor batch, nomor pengajuan, `client_request_id`, `source.handling_request_id`), teks (produk), dan majemuk (FEFO, monitoring, riwayat); daftar lengkap di SD 8.
- NFR-REL-01: Waktu disimpan UTC; tanggal bisnis memakai WIB.
- NFR-TEST-01: Aturan bisnis diuji dengan pytest + mongomock sesuai skenario SD 13.
- NFR-DEP-01: Berjalan lokal dengan `py main.py`; deploy menunggu konfirmasi dosen.

---

# 5. KRITERIA PENERIMAAN

- Login aman; hak akses per peran berjalan di server sesuai SD 4.2.
- Setiap stok masuk membuat batch baru; barang terjual per produk mengikuti FEFO; stok keluar tidak pernah membuat stok negatif; barang Expired/rusak tidak bisa keluar lewat jalur biasa.
- Barang rusak ditangani per buah; tanggal kedaluwarsa yang salah dapat dikoreksi dengan persetujuan Supervisor; stok menipis terlihat; login terlindung dari tebakan password.
- Status kedaluwarsa benar untuk semua batas (termasuk sisa 0 hari = Expired).
- Pemeriksaan tidak mengubah stok; selisih diperbaiki Staff lewat penyesuaian yang wajib berasal dari pemeriksaan; retur/pemusnahan wajib disetujui Supervisor.
- Rekomendasi tampil dengan alasan; batch Expired/tidak layak tidak pernah disarankan untuk dijual.
- Alur pengajuan lengkap (ajukan, setujui/tolak, selesaikan, batalkan) dengan riwayat; penyelesaian menghasilkan tepat satu pergerakan stok bila relevan.
- Sembilan laporan dan ekspor Excel menampilkan data nyata yang konsisten dengan riwayat pergerakan.
- Impor CSV strict dan tidak menggandakan data.
- `seed.py` menghasilkan demo multi user dan multi role.
- Tes otomatis untuk aturan bisnis lulus.

---

# 6. STATUS IMPLEMENTASI

**Diperbarui 14 November 2026 (versi 2.1).** Semua kebutuhan bagian 3 dan 4 sudah diimplementasikan dan diuji dengan 243 tes otomatis (pytest + mongomock). Tampilan diperiksa di Chrome tanpa jendela (lebar laptop 1366 px dan lebar ponsel 600 px) tanpa error JavaScript.

| Kelompok | Status |
|---|---|
| FR-AUTH, FR-RBAC, FR-USR | Selesai dan diuji |
| FR-PRD, FR-STK, FR-EXP | Selesai dan diuji |
| FR-INS, FR-REC, FR-REQ | Selesai dan diuji |
| FR-DSH, FR-RPT, FR-CSV, FR-AUD, FR-VAL, FR-SEED | Selesai dan diuji |
| NFR-UI (Webix, responsif) | Selesai; diperiksa di Chrome, belum di perangkat ponsel nyata |
| NFR-DATA, NFR-DB | Selesai; transaksi multi-dokumen dan indeks teks terbukti di MongoDB Atlas (14 Nov 2026) |
| NFR-DEP (deploy) | Belum; berjalan lokal, menunggu konfirmasi dosen |

Perubahan dibanding versi 1.2 tercantum di SD bagian 16.
