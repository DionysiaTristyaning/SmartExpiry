/* Riwayat Aktivitas (SD 5.6): siapa melakukan apa dan kapan (audit log). Supervisor dan Admin, hanya baca. */
(function () {
  "use strict";

  var esc = SE.esc;
  var list;

  function params() {
    return { actor_id: $$("acActor").getValue(), action: $$("acAction").getValue(),
      date_from: SE.dateOnly($$("acFrom").getValue()), date_to: SE.dateOnly($$("acTo").getValue()) };
  }

  /* Rincian ditulis dengan bahasa biasa. Data teknis (ID, sidik jari file, filter) tidak ditampilkan. */
  var DETAIL_LABEL = {
    request_number: "No. pengajuan", batch_number: "Kiriman", sku: "Kode produk", quantity: "Jumlah",
    handled_quantity: "Jumlah ditangani", expiry_date: "Kedaluwarsa", difference: "Selisih", is_fit: "Kondisi",
    type: "Jenis", movement_type: "Jenis", note: "Catatan", email: "Email", role: "Peran", old_role: "Peran lama",
    new_role: "Peran baru", name_changed: "Nama diubah", changed_fields: "Yang diubah", kind: "Data", rows: "Jumlah baris",
    reason: "Sebab", damaged_quantity: "Jumlah rusak", proposed_expiry_date: "Tanggal di kemasan",
    old_expiry_date: "Tanggal lama", new_expiry_date: "Tanggal baru", basis: "Barang", minutes: "Lama dikunci (menit)",
    rejected_quantity: "Ditolak saat datang", reject_reason: "Alasan ditolak"
  };
  var FIELD_LABEL = { name: "nama", category: "kategori", unit: "satuan", price: "harga", description: "deskripsi", min_stock: "stok minimum", pack_unit: "satuan besar", pack_size: "isi satuan besar",
    is_active: "status" };
  var KIND_LABEL = { products: "produk", stock: "stok", sales: "penjualan harian" };
  var LOGIN_REASON = { unknown_email: "email tidak terdaftar", inactive: "akun nonaktif", bad_password: "password salah",
    locked: "akun sedang dikunci" };
  var REPORT_LABEL = { "stock-products": "Stok produk", "stock-batches": "Stok per kiriman", "near-expiry": "Mendekati kedaluwarsa",
    expired: "Produk kedaluwarsa", movements: "Riwayat stok masuk & keluar", adjustments: "Riwayat penyamaan stok",
    inspections: "Riwayat cek fisik", requests: "Riwayat pengajuan" };

  function detailValue(k, v, o) {
    if (k === "is_fit") { return v ? "Layak" : "Tidak layak"; }
    if (k === "name_changed") { return v ? "ya" : "tidak"; }
    if (k === "role" || k === "old_role" || k === "new_role") { return SE.ROLE_LABEL[v] || v; }
    if (k === "type") { return SE.REQUEST_TYPE_LABEL[v] || v; }
    if (k === "basis") { return SE.BASIS_LABEL[v] || v; }
    if (k === "movement_type") { return SE.MOVEMENT_LABEL[v] || v; }
    if (k === "changed_fields") { return v.map(function (f) { return FIELD_LABEL[f] || f; }).join(", "); }
    if (k === "reason" && o.action === "login_failed") { return LOGIN_REASON[v] || v; }
    if (k === "kind") { return (o.action === "report_exported" ? REPORT_LABEL[v] : KIND_LABEL[v]) || v; }
    return Array.isArray(v) ? v.join(", ") : v;
  }

  function details(o) {
    var d = o.details || {}, parts = [];
    Object.keys(d).forEach(function (k) {
      var v = d[k];
      if (!DETAIL_LABEL[k] || v === null || v === "" || (Array.isArray(v) && !v.length)) { return; }
      if (typeof v === "object" && !Array.isArray(v)) { return; }
      parts.push(DETAIL_LABEL[k] + ": " + detailValue(k, v, o));
    });
    return parts.join(" · ") || "-";
  }

  function onShow() {
    SE.api("GET", "/api/v1/activity/options").then(function (res) {
      var a = $$("acActor"), b = $$("acAction");
      a.define("options", [{ id: SE.ALL, value: "Semua pengguna" }].concat(res.data.actors.map(function (u) { return { id: u.id, value: u.name }; })));
      b.define("options", [{ id: SE.ALL, value: "Semua aktivitas" }].concat(res.data.actions));
      a.refresh(); b.refresh();
    }).catch(function () { }).then(function () { list.reload(true); });
  }

  SE.register({
    id: "activity", title: "Riwayat Aktivitas", icon: "wxi-clock", order: 55, roles: ["supervisor", "admin"],
    build: function () {
      list = SE.pagedList({
        id: "act", url: "/api/v1/activity", params: params, rowHeight: 58, limit: 50, autoRowHeightColumn: "details",
        columns: [
          { id: "created_at", header: "Waktu", fillspace: 1.2, template: function (o) { return SE.dateTwoLine(o.created_at); } },
          { id: "actor_name", header: "Pengguna", fillspace: 1.4, template: function (o) {
            return SE.twoLine(o.actor_name, SE.ROLE_LABEL[o.actor_role] || "-"); } },
          { id: "action_label", header: "Aktivitas", fillspace: 1.6, template: function (o) { return esc(o.action_label); } },
          { id: "details", header: "Rincian", fillspace: 3.4, template: function (o) { return "<div class='long-text'>" + esc(details(o)) + "</div>"; } }
        ]
      });
      var dateCfg = { format: "%Y-%m-%d", stringResult: true, width: SE.isNarrow() ? 0 : 160,
        on: { onChange: function () { list.reload(true); } } };
      return SE.listPage({
        id: "activity", title: "Riwayat Aktivitas",
        subtitle: "Catatan siapa melakukan apa dan kapan. Catatan ini tidak bisa diubah atau dihapus.",
        onShow: onShow, list: list,
        filters: [
          { view: "richselect", id: "acActor", value: "", options: [{ id: SE.ALL, value: "Semua pengguna" }],
            on: { onChange: function () { list.reload(true); } } },
          { view: "richselect", id: "acAction", value: "", options: [{ id: SE.ALL, value: "Semua aktivitas" }],
            on: { onChange: function () { list.reload(true); } } },
          Object.assign({ view: "datepicker", id: "acFrom", placeholder: "Dari tanggal" }, dateCfg),
          Object.assign({ view: "datepicker", id: "acTo", placeholder: "Sampai tanggal" }, dateCfg)
        ]
      });
    }
  });
})();
