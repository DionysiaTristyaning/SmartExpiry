/* Rekomendasi (SD 5.5 B): saran berbasis aturan sederhana (bukan AI), satu per batch berstok, dihitung setiap
   kali halaman dibuka. Hanya saran: tidak mengubah stok dan tidak menjalankan tindakan apa pun. */
(function () {
  "use strict";

  var esc = SE.esc;
  var list;

  var ACTION_LABEL = {
    withdraw: "Ambil dari rak, ajukan penanganan",
    separate: "Pisahkan barang rusak",
    prioritize_handling: "Segera tangani",
    prioritize_sale: "Jual lebih dulu",
    monitor_fefo: "Pantau",
    no_action: "Tidak perlu tindakan"
  };

  function params() { return { action: $$("rAction").getValue() }; }

  function actionCell(o) {
    var extra = o.open_request_count > 0 ? "<small>(sudah ada pengajuan)</small>" : "";
    return "<div class='cell2'>" + SE.badge("ac-" + o.action, ACTION_LABEL[o.action] || o.action) + extra + "</div>";
  }

  function buttonsCell(o) {
    var html = "";
    if ((SE.isStaff() || SE.isSupervisor()) && o.action === "prioritize_handling" && !o.last_inspection) {
      html += "<span class='act act-inspect'>Cek fisik</span>";
    }
    if (SE.isStaff() && o.needs_request && !o.open_request_count) {
      html += "<span class='act act-danger act-request'>Buat pengajuan</span>";
    }
    return html;
  }

  SE.register({
    id: "recommendations", title: "Saran Tindakan", icon: "wxi-eye", order: 35,
    build: function () {
      list = SE.pagedList({
        id: "rec", url: "/api/v1/recommendations", params: params, rowHeight: 84, autoRowHeightColumn: "reason",
        columns: [
          { id: "action", header: "Saran", width: 190, template: actionCell },
          { id: "product_name", header: "Produk", fillspace: 2, minWidth: 185, template: function (o) {
            return SE.twoLine(o.product_name, o.sku + " · " + o.batch_number); } },
          { id: "expiry_status", header: "Status dan stok", width: 175, template: function (o) {
            return "<div class='cell2'>" + SE.statusBadge(o.expiry_status) + "<small>" + esc(SE.daysText(o)) +
              " · stok " + esc(o.current_quantity) + "</small></div>"; } },
          { id: "reason", header: "Alasan", fillspace: 3.4, minWidth: 230,
            template: function (o) { return "<div class='long-text'>" + esc(o.reason) + "</div>"; } },
          { id: "actions", header: "", width: 150, template: buttonsCell }
        ],
        onRowClick: function (item) { SE.openBatchDetail(item.id); },
        onClick: {
          "act-inspect": function (e, id) { SE.openInspectionForm(this.getItem(id), function () { list.reload(); }); return false; },
          "act-request": function (e, id) {
            var item = this.getItem(id);
            SE.openRequestForm(item, { reason: item.reason }, function () { list.reload(); });
            return false;
          }
        }
      });

      return SE.listPage({
        id: "recommendations", title: "Saran Tindakan",
        subtitle: "Saran untuk setiap kiriman, dilihat dari sisa hari sebelum kedaluwarsa dan hasil cek fisik terakhir. Keputusan tetap di tangan Anda.",
        onShow: function () { list.reload(true); }, list: list,
        filters: [
          { view: "richselect", id: "rAction", value: "", width: SE.isNarrow() ? 0 : 280,
            options: [{ id: "", value: "Semua saran" }].concat(Object.keys(ACTION_LABEL).map(function (k) {
              return { id: k, value: ACTION_LABEL[k] }; })), on: { onChange: function () { list.reload(true); } } }
        ]
      });
    }
  });
})();
