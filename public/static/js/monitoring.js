/* Monitoring Kedaluwarsa (SD 5.4): batch Monitoring, Near Expired, Critical, dan Expired yang masih berstok,
   yang paling dekat kedaluwarsa di atas. Batch yang kedaluwarsa hari ini sudah Expired. */
(function () {
  "use strict";

  var esc = SE.esc;
  var list;

  var VIEWS = [
    { id: "", value: "Semua" },
    { id: "check_due", value: "Perlu dicek" },
    { id: "monitoring", value: "Dipantau" },
    { id: "near_expired", value: "Hampir Kedaluwarsa" },
    { id: "critical", value: "Kritis" },
    { id: "expired", value: "Kedaluwarsa" }
  ];

  function params() { return { status: $$("monView").getValue() }; }

  function actions(o) {
    var html = "";
    if (SE.isStaff() || SE.isSupervisor()) { html += "<span class='act act-inspect'>Cek fisik</span>"; }
    if (SE.isStaff() && SE.requestable(o).some(function (r) { return r.basis !== "near_expiry"; })) {
      html += "<span class='act act-danger act-request'>Ajukan</span>";
    } else if ((o.open_requests || []).length) {
      /* sudah ada pengajuan yang belum selesai: tampilkan nomornya, klik untuk membuka */
      html += "<span class='act act-open-request' title='" + esc(SE.openRequestText(o)) + "'>Sudah diajukan</span>";
    }
    return html;
  }

  SE.register({
    id: "monitoring", title: "Pantau Kedaluwarsa", icon: "wxi-alert", order: 25,
    build: function () {
      list = SE.pagedList({
        id: "mon", url: "/api/v1/expiry/alerts", params: params, rowHeight: 60,
        columns: [
          { id: "product_name", header: "Produk", fillspace: 2.6, template: function (o) {
            return SE.twoLine(o.product_name, o.sku + " · " + o.batch_number); } },
          { id: "expiry_date", header: "Kedaluwarsa", fillspace: 1.7, template: function (o) { return SE.twoLine(SE.fmtDate(o.expiry_date), SE.daysText(o), true); } },
          { id: "expiry_status", header: "Status", width: 165, template: function (o) { return SE.statusBadge(o.expiry_status); } },
          { id: "current_quantity", header: "Stok", fillspace: 0.7, css: { "text-align": "right" },
            template: function (o) { return esc(o.current_quantity); } },
          { id: "fitness", header: "Kondisi", width: 140, template: function (o) { return SE.fitnessBadge(o.fitness); } },
          { id: "last_checked_date", header: "Cek terakhir", fillspace: 1.9, template: function (o) {
            if (!o.last_checked_date) { return "-"; }
            var ago = o.days_since_check === 0 ? "hari ini" : o.days_since_check + " hari lalu";
            var main = o.last_inspection ? "dicek " + ago : "datang " + ago;
            return SE.twoLine(main, (o.check_due ? "perlu dicek · " : "") + "tiap " + o.check_interval_days + " hari", true); } },
          { id: "actions", header: "", width: 230, template: actions }
        ],
        onRowClick: function (item) { SE.openBatchDetail(item.id); },
        onClick: {
          "act-inspect": function (e, id) { SE.openInspectionForm(this.getItem(id), function () { list.reload(); }); return false; },
          "act-request": function (e, id) { SE.openRequestForm(this.getItem(id), null, function () { list.reload(); }); return false; },
          "act-open-request": function (e, id) { SE.openRequestDetail(this.getItem(id).open_requests[0].id); return false; }
        }
      });

      var viewControl = SE.isNarrow()
        ? { view: "richselect", id: "monView", value: "", options: VIEWS, minWidth: 180, on: { onChange: function () { list.reload(true); } } }
        : { view: "tabbar", id: "monView", value: "", options: VIEWS, tabMinWidth: 90, on: { onChange: function () { list.reload(true); } } };

      return SE.listPage({
        id: "monitoring", title: "Pantau Kedaluwarsa",
        subtitle: "Barang yang kedaluwarsa dalam 30 hari atau sudah lewat. Tab \"Perlu dicek\" = yang harus dicek fisik hari ini.",
        onShow: function () { list.reload(true); }, list: list, filters: [viewControl]
      });
    }
  });
})();
