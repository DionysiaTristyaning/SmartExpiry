/* Laporan (SD 5.6): sembilan laporan untuk Supervisor dan Admin, dihitung langsung dari data operasional,
   masing-masing dengan filter dan ekspor Excel (.xlsx) berisi semua baris yang cocok dengan filter. */
(function () {
  "use strict";

  var esc = SE.esc;
  var lists = {};

  var REPORTS = [
    { id: "stock-products", value: "Stok produk", filters: ["repCategory", "repActive"] },
    { id: "low-stock", value: "Stok menipis (perlu pesan ulang)", filters: ["repCategory"] },
    { id: "stock-batches", value: "Stok per kiriman", filters: ["repProduct", "repStatus", "repStock"] },
    { id: "near-expiry", value: "Mendekati kedaluwarsa", filters: ["repProduct", "repNear"] },
    { id: "expired", value: "Produk kedaluwarsa", filters: ["repProduct"] },
    { id: "movements", value: "Riwayat stok masuk & keluar", filters: ["repProduct", "repInOut", "repFrom", "repTo"] },
    { id: "adjustments", value: "Riwayat penyamaan stok", filters: ["repProduct", "repAdj", "repFrom", "repTo"] },
    { id: "inspections", value: "Riwayat cek fisik", filters: ["repProduct", "repFit", "repFrom", "repTo"] },
    { id: "requests", value: "Riwayat pengajuan", filters: ["repReqStatus", "repReqType", "repFrom", "repTo"] }
  ];
  var ALL_FILTERS = ["repCategory", "repActive", "repProduct", "repStatus", "repStock", "repNear", "repInOut", "repAdj",
    "repFit", "repReqStatus", "repReqType", "repFrom", "repTo"];

  function current() { return $$("repKind").getValue() || "stock-products"; }
  function spec() { return REPORTS.filter(function (r) { return r.id === current(); })[0]; }
  function val(id) { return $$(id) && $$(id).isVisible() ? $$(id).getValue() : ""; }

  function params() {
    return {
      category: val("repCategory"), is_active: val("repActive"), product_id: val("repProduct"),
      status: val("repStatus") || val("repNear") || val("repReqStatus"), has_stock: val("repStock"),
      movement_type: val("repInOut") || val("repAdj"), fitness: val("repFit"), request_type: val("repReqType"),
      date_from: SE.dateOnly(val("repFrom")), date_to: SE.dateOnly(val("repTo"))
    };
  }

  function summary(html, res) {
    /* generated_at dari server: "2026-11-16 22:06" -> "16 Nov 2026 22.06" */
    var stamp = String(res.generated_at || "").split(" ");
    var when = stamp.length === 2 ? SE.fmtDate(stamp[0]) + " " + stamp[1].replace(":", ".") : res.generated_at;
    $$("repSummary").setHTML("<div class='sum-in'>" + html + " &nbsp;&middot;&nbsp; <span class='muted'>data per " +
      esc(when) + " WIB</span></div>");
  }

  function num(n) { return "<b>" + esc(n) + "</b>"; }

  function batchColumns() {
    return [
      { id: "product_name", header: "Produk", fillspace: 2.6, template: function (o) { return SE.twoLine(o.product_name, o.sku + " · " + o.batch_number); } },
      { id: "expiry_date", header: "Kedaluwarsa", fillspace: 1.6, template: function (o) { return SE.twoLine(SE.fmtDate(o.expiry_date), SE.daysText(o), true); } },
      { id: "expiry_status", header: "Status", width: 165, template: function (o) { return SE.statusBadge(o.expiry_status); } },
      { id: "current_quantity", header: "Stok", fillspace: 0.8, css: { "text-align": "right" }, template: function (o) { return esc(o.current_quantity) + " " + esc(o.unit); } },
      { id: "fitness", header: "Kondisi", width: 150, template: function (o) {
        return SE.fitnessBadge(o.fitness) + (o.damaged_quantity ? " <small>" + esc(o.damaged_quantity) + " rusak</small>" : ""); } }
    ];
  }

  function statusSummary(s) {
    return Object.keys(s).map(function (k) { return SE.statusBadge(k) + " " + num(s[k].batches) + " kiriman (" + esc(s[k].units) + " unit)"; })
      .join(" &nbsp; ");
  }

  function movementColumns() {
    return [
      { id: "movement_date", header: "Tanggal", fillspace: 1.3, template: function (o) { return esc(SE.fmtDate(o.movement_date)); } },
      { id: "product_name", header: "Produk", fillspace: 2.4, template: function (o) { return SE.twoLine(o.product_name, o.sku + " · " + o.batch_number); } },
      { id: "movement_type", header: "Jenis", fillspace: 2, template: function (o) { return esc(SE.MOVEMENT_LABEL[o.movement_type]); } },
      { id: "signed_quantity", header: "Jumlah", fillspace: 0.8, css: { "text-align": "right" }, template: function (o) { return (o.signed_quantity > 0 ? "+" : "") + esc(o.signed_quantity); } },
      { id: "quantity_after", header: "Perubahan stok", fillspace: 1.3, template: function (o) { return esc(o.quantity_before) + " &rarr; " + esc(o.quantity_after); } },
      { id: "reason", header: "Keterangan", fillspace: 2, template: function (o) { return esc(o.request_number || o.reason || o.notes || (o.movement_type === "stock_out" ? "Terjual" : "-")); } },
      { id: "created_by_name", header: "Oleh", fillspace: 1.1, template: function (o) { return esc(o.created_by_name); } }
    ];
  }

  var DEF = {
    "stock-products": {
      columns: [
        { id: "product_name", header: "Produk", fillspace: 2.6, template: function (o) { return SE.twoLine(o.product_name, o.sku + " · " + o.category); } },
        { id: "price", header: "Harga", fillspace: 1, css: { "text-align": "right" }, template: function (o) { return esc(SE.rupiah(o.price)); } },
        { id: "batch_count", header: "Kiriman", fillspace: 0.6, css: { "text-align": "right" }, template: function (o) { return esc(o.batch_count); } },
        { id: "available_stock", header: "Bisa dijual", fillspace: 1, css: { "text-align": "right" }, template: function (o) {
          var low = o.low_stock ? " <span class='badge fit-unfit'>menipis</span>" : "";
          return esc(o.available_stock) + " " + esc(o.unit) + low; } },
        { id: "min_stock", header: "Stok min.", fillspace: 0.7, css: { "text-align": "right" }, template: function (o) { return o.min_stock ? esc(o.min_stock) : "-"; } },
        { id: "damaged_units", header: "Rusak", fillspace: 0.6, css: { "text-align": "right" }, template: function (o) { return esc(o.damaged_units); } },
        { id: "expired_units", header: "Jumlah Kedaluwarsa", fillspace: 0.9, css: { "text-align": "right" }, template: function (o) { return esc(o.expired_units); } },
        { id: "nearest_expiry", header: "Kedaluwarsa terdekat", fillspace: 1.8, template: function (o) {
          return o.nearest_expiry ? SE.twoLine(SE.fmtDate(o.nearest_expiry), SE.daysText(o), true) : "-"; } },
        { id: "is_active", header: "Status", width: 110, template: function (o) { return SE.activeBadge(o.is_active); } }
      ],
      summary: function (s) {
        return num(s.products) + " produk &middot; bisa dijual " + num(s.available_stock) + " &middot; rusak " + num(s.damaged_units) +
          " &middot; Kedaluwarsa " + num(s.expired_units) + " &middot; stok menipis " + num(s.low_stock) + " produk";
      }
    },
    "low-stock": {
      columns: [
        { id: "product_name", header: "Produk", fillspace: 2.6, template: function (o) { return SE.twoLine(o.product_name, o.sku + " · " + o.category); } },
        { id: "available_stock", header: "Bisa dijual", fillspace: 1, css: { "text-align": "right" }, template: function (o) { return esc(o.available_stock) + " " + esc(o.unit); } },
        { id: "min_stock", header: "Stok minimum", fillspace: 1, css: { "text-align": "right" }, template: function (o) { return esc(o.min_stock); } },
        { id: "shortage", header: "Kekurangan", fillspace: 1, css: { "text-align": "right" }, template: function (o) { return "<b>" + esc(o.shortage) + "</b>"; } }
      ],
      summary: function (s) {
        return num(s.products) + " produk stoknya di bawah/sama dengan stok minimum &middot; total kekurangan " + num(s.shortage) +
          " &middot; <span class='muted'>stok minimum diatur di Data Produk</span>";
      }
    },
    "stock-batches": { columns: batchColumns(), summary: statusSummary },
    "near-expiry": { columns: batchColumns(), summary: statusSummary },
    "expired": { columns: batchColumns(), summary: statusSummary },
    "movements": { columns: movementColumns(), summary: function (s) { return "Total masuk " + num(s.stock_in) + " &middot; total keluar " + num(s.stock_out); } },
    "adjustments": { columns: movementColumns(), summary: function (s) { return "Stok ditambah " + num(s.adjustment_in) + " &middot; dikurangi " + num(s.adjustment_out); } },
    "inspections": {
      columns: [
        { id: "inspected_at", header: "Waktu", fillspace: 1.2, template: function (o) { return SE.dateTwoLine(o.inspected_at); } },
        { id: "product_name", header: "Produk", fillspace: 2.4, template: function (o) { return SE.twoLine(o.product_name, o.sku + " · " + o.batch_number); } },
        { id: "difference", header: "Tercatat → Dihitung", fillspace: 1.3, template: function (o) { return esc(o.system_quantity) + " &rarr; " + esc(o.physical_quantity); } },
        { id: "is_fit", header: "Kondisi", width: 120, template: function (o) {
          return o.is_fit ? SE.fitnessBadge("fit") : SE.badge("fit-unfit", o.damaged_quantity + " rusak"); } },
        { id: "label", header: "Tanggal di kemasan", fillspace: 1.4, template: function (o) {
          var fix = o.expiry_correction;
          return fix ? SE.twoLine(SE.fmtDate(fix.proposed_date), SE.CORRECTION_LABEL[fix.status], true) : "Sesuai"; } },
        { id: "notes", header: "Catatan", fillspace: 2, template: function (o) { return esc(o.notes) || "-"; } },
        { id: "inspected_by_name", header: "Oleh", fillspace: 1.1, template: function (o) { return esc(o.inspected_by_name); } }
      ],
      summary: function (s) {
        return num(s.inspections) + " kali cek &middot; ada yang rusak " + num(s.unfit) + " &middot; jumlahnya berbeda " +
          num(s.with_difference) + " &middot; tanggal di kemasan berbeda " + num(s.corrections);
      }
    },
    "requests": {
      columns: [
        { id: "request_number", header: "Nomor", fillspace: 1.4, template: function (o) { return esc(o.request_number); } },
        { id: "submitted_at", header: "Diajukan", fillspace: 1.2, template: function (o) { return SE.dateTwoLine(o.submitted_at); } },
        { id: "product_name", header: "Produk", fillspace: 2.2, template: function (o) { return SE.twoLine(o.product_name, o.batch_number); } },
        { id: "request_type", header: "Jenis", fillspace: 1.9, template: function (o) { return SE.twoLine(SE.REQUEST_TYPE_LABEL[o.request_type], o.basis_label || "-"); } },
        { id: "quantity", header: "Jumlah", fillspace: 0.7, css: { "text-align": "right" }, template: function (o) { return esc(o.quantity) + (o.handled_quantity != null ? " / " + esc(o.handled_quantity) : ""); } },
        { id: "status", header: "Status", width: 130, template: function (o) { return SE.requestBadge(o.status); } },
        { id: "submitted_by_name", header: "Pengaju", fillspace: 1.1, template: function (o) { return esc(o.submitted_by_name); } }
      ],
      summary: function (s) { return Object.keys(s).map(function (k) { return SE.requestBadge(k) + " " + num(s[k]); }).join(" &nbsp; "); }
    }
  };

  function reload() {
    var kind = current();
    ALL_FILTERS.forEach(function (id) { if (spec().filters.indexOf(id) === -1) { $$(id).hide(); } else { $$(id).show(); } });
    $$("repCells").setValue("cell_" + kind);
    lists[kind].reload(true);
  }

  /* Dipanggil dari kartu dashboard: buka laporan tertentu. */
  SE.openReport = function (kind) {
    if ($$("repKind") && kind) { $$("repKind").setValue(kind); }
  };

  function onShow() {
    SE.api("GET", "/api/v1/products?sort=name&limit=100").then(function (res) {
      var f = $$("repProduct");
      f.define("options", [{ id: SE.ALL, value: "Semua produk" }].concat(res.data.map(function (p) { return { id: p.id, value: p.sku + " - " + p.name }; })));
      f.refresh();
      return SE.api("GET", "/api/v1/products/categories");
    }).then(function (res) {
      var f = $$("repCategory"), cur = f.getValue();
      f.define("options", [{ id: SE.ALL, value: "Semua kategori" }].concat(res.data.map(function (c) { return { id: c, value: c }; })));
      f.refresh(); f.setValue(cur || "");
    }).catch(function (err) { SE.toast(err.message, "error"); }).then(reload);
  }

  function exportButton() {
    return { view: "button", value: "Unduh Excel", width: 130, tooltip: "Unduh laporan ini (sesuai pilihan di atas) sebagai file Excel",
      click: function () {
        var btn = this, q = SE.query(params());
        btn.disable();
        SE.download("/api/v1/reports/" + current() + "/export" + (q ? "?" + q : "")).then(function (name) {
          SE.toast("File " + name + " sudah diunduh.");
        }).catch(function (err) { SE.toast(err.message, "error"); }).then(function () { btn.enable(); });
      } };
  }

  function select(id, options, extra) {
    return Object.assign({ view: "richselect", id: id, value: "", options: options, hidden: true,
      on: { onChange: function () { lists[current()].reload(true); } } }, extra || {});
  }

  SE.register({
    id: "reports", title: "Laporan", icon: "wxi-file", order: 50, roles: ["supervisor", "admin"],
    build: function () {
      REPORTS.forEach(function (r) {
        lists[r.id] = SE.pagedList({ id: "rep_" + r.id.replace(/-/g, "_"), url: "/api/v1/reports/" + r.id, params: params,
          rowHeight: 58, columns: DEF[r.id].columns,
          onData: function (res) { summary(DEF[r.id].summary(res.summary), res); } });
      });
      var statusOpts = [{ id: SE.ALL, value: "Semua status" }].concat(SE.STATUS_ORDER.map(function (s) { return { id: s, value: SE.STATUS_LABEL[s] }; }));
      var dateCfg = { format: "%Y-%m-%d", stringResult: true, width: SE.isNarrow() ? 0 : 160 };

      return SE.listPage({
        id: "reports", title: "Laporan", subtitle: "Pilih jenis laporan, atur pilihan di sebelahnya, lalu unduh ke Excel bila perlu.",
        onShow: onShow, buttons: [exportButton()],
        filters: [
          { view: "richselect", id: "repKind", value: "stock-products", options: REPORTS, width: SE.isNarrow() ? 0 : 270, minWidth: 190,
            on: { onChange: reload } },
          { view: "combo", id: "repProduct", value: "", placeholder: "Semua produk", options: [], hidden: true, width: SE.isNarrow() ? 0 : 230,
            on: { onChange: function () { lists[current()].reload(true); } } },
          select("repCategory", [{ id: SE.ALL, value: "Semua kategori" }]),
          select("repActive", [{ id: SE.ALL, value: "Aktif & nonaktif" }, { id: "true", value: "Aktif" }, { id: "false", value: "Nonaktif" }]),
          select("repStatus", statusOpts),
          select("repStock", [{ id: SE.ALL, value: "Ada stok & habis" }, { id: "true", value: "Masih ada stok" }, { id: "false", value: "Stok habis" }]),
          select("repNear", [{ id: SE.ALL, value: "Hampir Kedaluwarsa + Kritis" }, { id: "near_expired", value: "Hampir Kedaluwarsa" }, { id: "critical", value: "Kritis" }]),
          select("repInOut", [{ id: SE.ALL, value: "Masuk & keluar" }, { id: "stock_in", value: "Stok masuk" }, { id: "stock_out", value: "Stok keluar" }]),
          select("repAdj", [{ id: SE.ALL, value: "Ditambah & dikurangi" }, { id: "adjustment_in", value: "Stok disamakan (tambah)" }, { id: "adjustment_out", value: "Stok disamakan (kurang)" }]),
          select("repFit", [{ id: SE.ALL, value: "Semua kondisi" }, { id: "fit", value: "Layak" }, { id: "unfit", value: "Ada yang rusak" }]),
          select("repReqStatus", [{ id: SE.ALL, value: "Semua status" }].concat(Object.keys(SE.REQUEST_STATUS_LABEL).map(function (k) { return { id: k, value: SE.REQUEST_STATUS_LABEL[k] }; }))),
          select("repReqType", [{ id: SE.ALL, value: "Semua jenis" }, { id: "return", value: "Pengembalian" }, { id: "disposal", value: "Pemusnahan" }]),
          Object.assign({ view: "datepicker", id: "repFrom", placeholder: "Dari tanggal", hidden: true,
            on: { onChange: function () { lists[current()].reload(true); } } }, dateCfg),
          Object.assign({ view: "datepicker", id: "repTo", placeholder: "Sampai tanggal", hidden: true,
            on: { onChange: function () { lists[current()].reload(true); } } }, dateCfg)
        ],
        before: [{ view: "template", id: "repSummary", borderless: true, autoheight: true, css: "summary-line", height: SE.isNarrow() ? 84 : 52, template: "" }],
        body: { view: "multiview", id: "repCells", animate: false, cells: REPORTS.map(function (r) {
          return { id: "cell_" + r.id, rows: lists[r.id].ui.rows };
        }) }
      });
    }
  });
})();
