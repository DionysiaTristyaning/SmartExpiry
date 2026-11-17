/* Panduan singkat per peran (tombol "Panduan" di toolbar): tugas sehari-hari dan di menu mana mengerjakannya.
   Isinya teks tetap dari kode (bukan isian pengguna). */
(function () {
  "use strict";

  function m(name) { return "<span class='menu'>" + name + "</span>"; }

  var STATUS = "<h3>Arti status kedaluwarsa</h3><ul>" +
    "<li>Aman: masih lebih dari 3 bulan (90 hari).</li>" +
    "<li>Perlu Dipantau: 1 sampai 3 bulan lagi (31 sampai 90 hari). Dicek berkala dan dijual sesuai urutan, yang paling dulu kedaluwarsa dijual lebih dulu.</li>" +
    "<li>Kritis: 1 bulan terakhir (1 sampai 30 hari). Taruh di depan rak, jual lebih dulu, dan dicek lebih sering. Kalau tidak akan terjual, ajukan pengembalian ke pemasok.</li>" +
    "<li>Kedaluwarsa: hari ini atau sudah lewat. Tidak boleh dijual dan harus diajukan pengembalian atau pemusnahan.</li></ul>" +
    "<h3>Istilah</h3><ul>" +
    "<li>Kiriman: barang yang datang bersamaan dengan tanggal kedaluwarsa yang sama. Setiap barang datang dicatat sebagai satu kiriman dengan nomor otomatis.</li>" +
    "<li>Stok disamakan: stok di aplikasi diubah sesuai hasil hitungan di rak.</li>" +
    "<li>Pengembalian: barang dikembalikan ke pemasok. Pemusnahan: barang dibuang atau dirusak dengan disaksikan.</li></ul>";

  var GUIDES = {
    staff: "<h3>Tugas Staff</h3><ol>" +
      "<li>Barang datang dari pemasok: menu " + m("Stok Barang") + ", tombol <b>+ Barang Datang</b>. Barang yang rusak saat datang diisi di kolom ditolak.</li>" +
      "<li>Barang terjual: menu " + m("Keluar-Masuk Stok") + ", tombol <b>+ Catat Terjual</b>. Untuk banyak produk sekaligus, pakai <b>Impor File</b>.</li>" +
      "<li>Cek fisik di rak: menu " + m("Pantau Kedaluwarsa") + ", tab <b>Perlu dicek</b>, lalu klik <b>Cek fisik</b> pada barangnya. Kalau jumlahnya berbeda, pilih <b>Samakan stok</b>.</li>" +
      "<li>Barang kedaluwarsa atau kritis: klik <b>Ajukan</b> di " + m("Pantau Kedaluwarsa") + " atau " + m("Saran Tindakan") + ", lalu tunggu persetujuan Supervisor.</li>" +
      "<li>Menemukan barang rusak di rak (barang apa pun, termasuk yang belum kedaluwarsa): buka menu " + m("Pengajuan") + ", klik <b>+ Ajukan</b>, pilih produk dan kirimannya, pilih <b>Barang rusak</b>, lalu isi jumlah dan alasannya. Jumlah itu langsung <b>ditahan</b> (tidak bisa dijual) sampai pengajuannya selesai atau ditolak.</li>" +
      "<li>Pengajuan yang sudah disetujui: kembalikan ke pemasok atau musnahkan barangnya, lalu buka menu " + m("Pengajuan") + " dan klik <b>Selesaikan</b>. Stok berkurang otomatis.</li></ol>" +
      "<h3>Isi lonceng</h3><ul>" +
      "<li>Kiriman perlu dicek fisik: sudah waktunya dicek menurut jadwal.</li>" +
      "<li>Disetujui, belum diselesaikan: barangnya harus dikembalikan atau dimusnahkan, lalu ditandai Selesai.</li>" +
      "<li>Pengajuan ditolak: alasan penolakan ada di rincian pengajuan.</li></ul>",

    supervisor: "<h3>Tugas Supervisor</h3><ol>" +
      "<li>Menyetujui pengajuan: klik lonceng atau buka menu " + m("Pengajuan") + ", lalu pilih <b>Setujui</b> atau <b>Tolak</b>. Alasan wajib diisi saat menolak.</li>" +
      "<li>Koreksi tanggal kedaluwarsa: menu " + m("Pemeriksaan Stok") + ", pilih <b>Setujui tanggal</b> atau <b>Tolak</b>. Usulan dari cek fisik Anda sendiri diputuskan oleh Supervisor lain.</li>" +
      "<li>Cek silang: Anda juga boleh melakukan <b>Cek fisik</b> di " + m("Pantau Kedaluwarsa") + ". Pemberitahuan \"Stok disamakan\" di lonceng hilang setelah Anda mengecek fisik kiriman itu.</li>" +
      "<li>Pengawasan: kartu di " + m("Dashboard") + ", menu " + m("Laporan") + " dan " + m("Riwayat Aktivitas") + ".</li>" +
      "<li>Data produk dan stok minimum: menu " + m("Data Produk") + ".</li></ol>" +
      "<p>Mencatat barang datang, barang terjual, dan menyamakan stok adalah tugas Staff.</p>",

    admin: "<h3>Tugas Admin</h3><ol>" +
      "<li>Akun karyawan: menu " + m("Pengguna") + ", tombol <b>+ Tambah Pengguna</b>. Dari rincian akun, Admin bisa mengganti password (sekaligus membuka akun yang terkunci) atau menonaktifkan akun.</li>" +
      "<li>Data produk: tambah atau ubah di menu " + m("Data Produk") + ".</li>" +
      "<li>Pengawasan: menu " + m("Laporan") + " dan " + m("Riwayat Aktivitas") + ", serta lonceng untuk stok yang disamakan Staff.</li></ol>" +
      "<p>Admin tidak mencatat stok dan tidak menyetujui pengajuan.</p>"
  };

  SE.openGuide = function () {
    if ($$("winGuide")) { $$("winGuide").close(); }
    var role = SE.me.role;
    webix.ui({
      view: "window", id: "winGuide", modal: true, position: "center", move: true,
      width: Math.min(620, window.innerWidth - 20), head: "Panduan " + SE.ROLE_LABEL[role],
      body: { rows: [
        { view: "template", borderless: true, scroll: "y", height: Math.min(560, window.innerHeight - 140),
          template: "<div class='guide'>" + (GUIDES[role] || "") + STATUS + "</div>" },
        { padding: 12, cols: [{}, { view: "button", value: "Tutup", css: "webix_primary", width: 110,
          click: function () { $$("winGuide").close(); } }] }
      ] }
    }).show();
  };

  SE.guideButton = function () {
    /* di HP cukup tanda "?" supaya toolbar tidak penuh */
    return { view: "button", value: SE.isNarrow() ? "?" : "Panduan", css: "ghost-btn", width: SE.isNarrow() ? 40 : 96,
      tooltip: "Cara memakai aplikasi untuk peran Anda", click: SE.openGuide };
  };
})();
