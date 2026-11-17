/* Notifikasi di dalam aplikasi (lonceng di toolbar). Isinya dihitung server saat diminta; tidak ada yang disimpan.
   Supervisor: pengajuan yang menunggu persetujuan, usulan koreksi tanggal, dan penyesuaian stok 7 hari terakhir
   yang belum dicek ulang (hilang setelah Supervisor mengecek fisik kirimannya). Admin: penyesuaian stok yang
   belum dicek ulang (pengawasan). Staff: pengajuan disetujui yang belum
   diselesaikan dan pengajuannya yang ditolak (7 hari). Bukan email/WhatsApp/SMS. */
(function () {
  "use strict";

  var esc = SE.esc;
  var items = [];
  var timer = null;

  var BELL = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>' +
    '<path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>';

  SE.bellButton = function () {
    return { view: "button", id: "bellBtn", type: "htmlbutton", css: "bell-btn", width: SE.isNarrow() ? 44 : 52, label: BELL,
      /* Ambil data terbaru dulu, supaya pemberitahuan yang sudah ditangani tidak muncul lagi. */
      tooltip: "Pemberitahuan", click: function () { SE.refreshNotifications().then(show); } };
  };

  function paintBadge() {
    var label = BELL + (items.length ? '<span class="bell-count">' + (items.length > 9 ? "9+" : items.length) + "</span>" : "");
    var btn = $$("bellBtn");
    if (btn) { btn.define("label", label); btn.refresh(); }
  }

  SE.refreshNotifications = function () {
    return SE.api("GET", "/api/v1/notifications", undefined, true).then(function (res) {
      items = res.data.items || [];
      paintBadge();
    }).catch(function () { });
  };

  SE.startNotifications = function () {
    SE.refreshNotifications();
    if (timer) { clearInterval(timer); }
    timer = setInterval(SE.refreshNotifications, 60000);
  };

  function itemHtml(n) {
    return '<div class="notif notif-' + esc(n.kind) + '"><b>' + esc(n.title) + "</b><span>" + esc(n.text) +
      "</span><small>" + esc(SE.fmtDateTime(n.at)) + "</small></div>";
  }

  function show() {
    if ($$("notifPopup")) { $$("notifPopup").close(); }
    var body;
    if (!items.length) {
      body = { view: "template", borderless: true, height: 70, css: "notif-empty", template: "Belum ada pemberitahuan." };
    } else {
      body = {
        view: "list", id: "notifList", css: "notif-list", select: true, scroll: "y", data: items,
        height: Math.min(items.length * 90, 430, Math.max(window.innerHeight - 150, 120)) + 4, type: { height: 90 },
        template: function (n) { return itemHtml(n); },
        on: {
          onItemClick: function (id) {
            var n = this.getItem(id);
            $$("notifPopup").hide();
            if (n.request_id && SE.openRequestDetail) { SE.openRequestDetail(n.request_id); }
            else if (n.kind === "expiry_correction") { SE.go("inspections", "pending"); }
            else if (n.kind === "check_due") { SE.go("monitoring", "check_due"); }
            else if (n.batch_id && SE.openBatchDetail) { SE.openBatchDetail(n.batch_id); }
          }
        }
      };
    }
    var width = Math.min(380, window.innerWidth - 20);
    var popup = webix.ui({
      view: "popup", id: "notifPopup", width: width, css: "notif-popup", body: body,
      /* Di HP popup dipasang rata dengan tepi layar (10px dari kiri) supaya tidak terpotong. */
      position: function (state) { state.left = Math.max((window.innerWidth - width) / 2, 10); state.top = 62; }
    });
    if (SE.isNarrow()) { popup.show(); }
    else { popup.show($$("bellBtn").getNode(), { x: -(width - 52), y: 6 }); }
  }
})();
