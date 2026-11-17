/* Pengajuan (SD 5.5 C): penanganan barang kedaluwarsa / mendekati kedaluwarsa / rusak.
   Staff mengajukan retur atau pemusnahan -> Supervisor menyetujui atau menolak -> barang ditangani secara fisik
   (di luar aplikasi) -> Staff mana pun menandai Selesai -> sistem mencatat stok keluar otomatis. */
(function () {
  "use strict";

  var esc = SE.esc, api = SE.api, toast = SE.toast;
  var list;

  var HISTORY_LABEL = { submitted: "Diajukan", approved: "Disetujui", rejected: "Ditolak", cancelled: "Dibatalkan",
    completed: "Diselesaikan" };

  function params() { return { status: $$("rqStatus").getValue(), request_type: $$("rqType").getValue() }; }

  function refreshAll(done) {
    SE.refreshNotifications();
    (done || function () { list.reload(); })();
  }

  /* ---------- ajukan (Staff) ---------- */
  /* Pilihan "barang yang diajukan" dihitung server (request_options):
       expired     -> batch Expired: seluruh stok, retur atau pemusnahan
       damaged     -> barang rusak dari cek fisik: semua barang rusak itu, retur atau pemusnahan
       near_expiry -> batch Critical (1 bulan terakhir): barang yang masih bagus, boleh sebagian, HANYA retur */
  var BASIS_TEXT = {
    expired: "Barang sudah kedaluwarsa, jadi semua sisa stoknya harus ditangani. Utamakan dikembalikan ke pemasok; kalau pemasok tidak mau menerima, musnahkan.",
    damaged: "Hanya barang yang rusak yang ditangani, semuanya sekaligus. Barang lain di kiriman ini tetap boleh dijual.",
    damaged_direct: "Isi jumlah barang yang rusak. Jumlah itu langsung <b>ditahan</b> (tidak bisa dijual) sampai pengajuannya " +
      "selesai atau ditolak. Barang lain di kiriman ini tetap boleh dijual.",
    near_expiry: "Barang masih bagus, jadi hanya boleh dikembalikan ke pemasok (boleh sebagian). Barang yang masih bagus tidak dimusnahkan."
  };
  function basisOption(o, unit) {
    var label = o.direct ? "Lapor barang rusak" : SE.BASIS_LABEL[o.basis];
    return { id: o.basis, value: label + " (" + (o.fixed ? "" : "paling banyak ") + o.quantity + " " + unit + ")" };
  }

  SE.openRequestForm = function (batch, defaults, onDone) {
    var d = defaults || {};
    var requestId = SE.uuid();
    var current = null;

    function applyBasis(basis) {
      var hint = $$("rqHint"), qty = $$("rqQty"), type = $$("rqFormType");
      if (!hint || !qty || !type || !current) { return; }
      var option = (current.request_options || []).filter(function (o) { return o.basis === basis; })[0];
      var head = "Sisa stok kiriman: <b>" + esc(current.current_quantity) + " " + esc(current.unit) + "</b> &middot; " +
        esc(SE.STATUS_LABEL[current.expiry_status]) + " (" + esc(SE.daysText(current)) + ") &middot; " +
        esc(SE.FITNESS_LABEL[current.fitness]) + (current.damaged_quantity ? " (" + esc(current.damaged_quantity) + " rusak)" : "") +
        ((current.open_requests || []).length ? "<br>Sudah diajukan sebelumnya: " + esc(SE.openRequestText(current)) : "");
      if (!option) { hint.setHTML("<span class='form-hint'>" + head + "</span>"); return; }
      hint.setHTML("<span class='form-hint'>" + head + "<br>" + BASIS_TEXT[option.direct ? "damaged_direct" : basis] + "</span>");
      if (option.fixed) { qty.setValue(option.quantity); qty.disable(); }
      else {
        qty.enable();
        /* laporan rusak langsung: jumlah dikosongkan supaya staff mengisi sendiri (bukan otomatis semua stok) */
        qty.setValue(option.direct ? "" : option.quantity);
      }
      if (option.types.indexOf("disposal") < 0) { type.setValue("return"); type.disable(); } else { type.enable(); }
    }

    var picker = SE.batchPicker(batch, { mode: "stock", productSource: "requestable",
      filter: function (b) { return SE.requestable(b).length > 0; },
      emptyText: "Belum ada barang dari produk ini yang bisa diajukan (stoknya habis, atau seluruhnya sudah diajukan).",
      onBatch: function (b) {
        var basis = $$("rqBasis"), hint = $$("rqHint");
        if (!basis || !hint) { return; }
        current = b;
        var options = b ? SE.requestable(b) : [];  // yang masih terhalang pengajuan lain tidak ditawarkan
        basis.define("options", options.map(function (o) { return basisOption(o, b.unit); }));
        basis.refresh();
        if (!b) { hint.setHTML(""); basis.setValue(""); return; }
        if (!options.length) {
          hint.setHTML("<span class='form-hint warn'>" + ((b.open_requests || []).length
            ? "Kiriman ini sudah diajukan: " + esc(SE.openRequestText(b)) + ". Tunggu sampai pengajuan itu selesai " +
              "(atau dibatalkan) sebelum mengajukan lagi."
            : "Tidak ada barang di kiriman ini yang bisa diajukan.") + "</span>");
          basis.setValue(""); return;
        }
        /* pilihan biasa (kedaluwarsa, rusak tercatat, kritis) didahulukan; lapor rusak langsung dipilih sendiri */
        var preferred = options.filter(function (o) { return !o.direct; })[0] || options[0];
        basis.setValue(preferred.basis);
        applyBasis(preferred.basis);
      } });
    var win = SE.formWindow({ id: "winRequest", title: "Ajukan Pengembalian / Pemusnahan", width: 520, elements: [
      SE.tip("Pengajuan diperiksa Supervisor dulu. Setelah disetujui dan barangnya benar-benar dikembalikan atau dimusnahkan, " +
        "buka menu Pengajuan lalu klik Selesaikan. Stok baru berkurang saat itu. Barang rusak yang diajukan langsung " +
        "ditahan (tidak bisa dijual) selama menunggu.")
    ].concat(picker.elements, [
      { view: "richselect", id: "rqBasis", label: "Barang yang diajukan", options: [], value: "",
        on: { onChange: function (v) { applyBasis(v); } } },
      { view: "template", id: "rqHint", borderless: true, autoheight: true, template: "" },
      { view: "richselect", id: "rqFormType", name: "request_type", label: "Tindakan", value: d.request_type || "return",
        options: [{ id: "return", value: "Kembalikan ke pemasok" }, { id: "disposal", value: "Musnahkan (pilihan terakhir)" }] },
      { view: "text", id: "rqQty", name: "quantity", label: "Jumlah", type: "number", value: "" },
      { view: "textarea", name: "reason", label: "Alasan", height: 80, value: d.reason || "",
        placeholder: "Contoh: kedaluwarsa 13 Nov, 5 cup belum terjual" },
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winRequest").close(); } },
        { view: "button", value: "Ajukan", css: "webix_primary", click: function () {
          var v = $$("winRequestForm").getValues();
          var qty = $$("rqQty").getValue();  // field yang dikunci tidak ikut getValues, jadi dibaca langsung
          var body = { batch_id: batch ? batch.id : v.batch_id, basis: $$("rqBasis").getValue(),
            request_type: $$("rqFormType").getValue(), quantity: qty === "" ? "" : Number(qty), reason: v.reason,
            client_request_id: requestId };
          SE.busy(this, api("POST", "/api/v1/requests", body)).then(function (res) {
            $$("winRequest").close();
            toast("Pengajuan " + res.data.request_number + " terkirim. Tunggu persetujuan Supervisor.");
            refreshAll(onDone);
          }).catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ]) });
    win.show();
    picker.start();
  };

  /* ---------- setujui / tolak / batalkan (dengan catatan) ---------- */
  function decide(item, action, done) {
    var cfg = {
      approve: { title: "Setujui pengajuan", text: "Catatan (opsional):", ok: "Setujui", msg: "Pengajuan disetujui." },
      reject: { title: "Tolak pengajuan", text: "Alasan penolakan (wajib):", ok: "Tolak", msg: "Pengajuan ditolak." },
      cancel: { title: "Batalkan pengajuan", text: item.status === "approved" ? "Alasan pembatalan (wajib):" : "Catatan (opsional):",
        ok: "Batalkan pengajuan", msg: "Pengajuan dibatalkan." }
    }[action];
    webix.prompt({ title: cfg.title, text: esc(item.request_number) + "<br>" + cfg.text, ok: cfg.ok, cancel: "Kembali",
      input: { placeholder: "Catatan" } })
      .then(function (note) { return api("POST", "/api/v1/requests/" + item.id + "/" + action, { note: note || "" }); })
      .then(function () { toast(cfg.msg); refreshAll(done); })
      .catch(function (err) { if (err && err.message) { toast(err.message, "error"); } });
  }

  /* ---------- selesaikan (Staff mana pun) ---------- */
  function complete(item, done) {
    var handledText = item.request_type === "return" ? "dikembalikan ke pemasok" : "dimusnahkan";
    var win = SE.formWindow({ id: "winComplete", title: "Selesaikan " + item.request_number, width: 440, elements: [
      SE.tip("Isi setelah barangnya benar-benar " + handledText + ". Stok berkurang otomatis sebanyak jumlah yang diisi " +
        "(paling banyak " + esc(item.quantity) + ")."),
      { view: "text", name: "handled_quantity", label: "Jumlah yang benar-benar ditangani", type: "number", value: item.quantity },
      /* Bukti penanganan (setara berita acara sederhana), wajib diisi */
      { view: "textarea", name: "note", height: 90,
        label: item.request_type === "return" ? "Keterangan pengembalian (wajib): pemasok dan nomor dokumen" : "Keterangan pemusnahan (wajib): cara dan saksi",
        placeholder: item.request_type === "return"
          ? "Contoh: Dikembalikan ke PT Sumber Segar, surat jalan no. SJR-0112"
          : "Contoh: Kemasan dirusak lalu dibuang ke bak sampah belakang, disaksikan Andi (Supervisor)" },
      SE.note("Bila jumlahnya lebih sedikit dari yang disetujui, tulis juga alasannya."),
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winComplete").close(); } },
        { view: "button", value: "Tandai Selesai", css: "webix_primary", click: function () {
          var v = $$("winCompleteForm").getValues();
          SE.busy(this, api("POST", "/api/v1/requests/" + item.id + "/complete",
            { handled_quantity: v.handled_quantity === "" ? "" : Number(v.handled_quantity), note: v.note || "" }))
            .then(function () {
              $$("winComplete").close();
              toast("Pengajuan selesai. Stok sudah dikurangi otomatis.");
              refreshAll(done);
            }).catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ] });
    win.show();
  }

  function can(item) {
    return {
      review: SE.isSupervisor() && item.status === "pending" && item.submitted_by !== SE.me.id,
      cancelOwn: SE.isStaff() && item.status === "pending" && item.submitted_by === SE.me.id,
      cancelApproved: SE.isSupervisor() && item.status === "approved",
      complete: SE.isStaff() && item.status === "approved"
    };
  }

  function actionsCell(o) {
    var c = can(o), html = "";
    if (c.review) { html += "<span class='act act-approve'>Setujui</span><span class='act act-danger act-reject'>Tolak</span>"; }
    if (c.complete) { html += "<span class='act act-complete'>Selesaikan</span>"; }
    if (c.cancelOwn) { html += "<span class='act act-danger act-cancel'>Batalkan</span>"; }
    return html;
  }

  /* ---------- halaman detail ---------- */
  function openDetail(id) {
    api("GET", "/api/v1/requests/" + id).then(function (res) {
      var r = res.data;
      var reopen = function () { openDetail(r.id); };
      var who = function (name, at) { return name ? name + " (" + SE.fmtDateTime(at) + ")" : "-"; };
      var form = SE.detailForm({
        id: "rqForm", canEdit: false,
        values: {
          number: r.request_number, status: SE.REQUEST_STATUS_LABEL[r.status],
          type: SE.REQUEST_TYPE_LABEL[r.request_type] + " · " + (r.basis_label || "-"),
          product: r.product_name + " (" + r.sku + ")", batch: r.batch_number + " · kedaluwarsa " + SE.fmtDate(r.expiry_date) + " · stok " + r.batch_quantity,
          quantity: r.quantity + " " + r.unit, handled: r.handled_quantity != null ? r.handled_quantity + " " + r.unit : "-",
          reason: r.reason, submitted: who(r.submitted_by_name, r.submitted_at), reviewed: who(r.reviewed_by_name, r.reviewed_at),
          review_note: r.review_note || "-", completed: who(r.completed_by_name, r.completed_at)
        },
        rows: [
          [{ view: "text", name: "number", label: "Nomor" }, { view: "text", name: "status", label: "Status" }],
          [{ view: "text", name: "type", label: "Jenis" }, { view: "text", name: "product", label: "Produk" }],
          [{ view: "text", name: "batch", label: "Kiriman" }, { view: "text", name: "quantity", label: "Jumlah diajukan" }],
          [{ view: "text", name: "reason", label: "Alasan" }, { view: "text", name: "handled", label: "Jumlah ditangani" }],
          [{ view: "text", name: "submitted", label: "Diajukan oleh" }, { view: "text", name: "reviewed", label: "Ditinjau oleh" }],
          [{ view: "text", name: "review_note", label: "Catatan Supervisor" }, { view: "text", name: "completed", label: "Diselesaikan oleh" }]
        ]
      });

      var history = (r.history || []).map(function (h) {
        return { at: esc(SE.fmtDateTime(h.at)), action: esc(HISTORY_LABEL[h.action] || h.action),
          by: esc(h.by_name) + " <small style='color:#626b7a'>(" + esc(SE.ROLE_LABEL[h.role] || "-") + ")</small>",
          note: esc(h.note || "") };
      });
      var table = SE.detailTable("rqHistory", [
        { id: "at", header: "Waktu", width: 170 }, { id: "action", header: "Kejadian", width: 130 },
        { id: "by", header: "Dilakukan oleh", width: 240 }, { id: "note", header: "Catatan", fillspace: true, minWidth: 200 }
      ].map(function (c) { c.template = "#" + c.id + "#"; return c; }), history);

      var c = can(r), buttons = [];
      if (c.review) {
        buttons.push({ view: "button", value: "Tolak", css: "danger-btn", width: 90, click: function () { decide(r, "reject", reopen); } });
        buttons.push({ view: "button", value: "Setujui", css: "webix_primary", width: 100, click: function () { decide(r, "approve", reopen); } });
      }
      if (c.cancelOwn || c.cancelApproved) {
        buttons.push({ view: "button", value: "Batalkan", css: "danger-btn", width: 110, click: function () { decide(r, "cancel", reopen); } });
      }
      if (c.complete) {
        buttons.push({ view: "button", value: "Tandai Selesai", css: "webix_primary", width: 140, click: function () { complete(r, reopen); } });
      }

      SE.showDetail({
        parentId: "requests", parentTitle: "Pengajuan", title: r.request_number + " · " + SE.REQUEST_TYPE_LABEL[r.request_type],
        buttons: buttons, body: { rows: [form.ui, SE.sectionTitle("Riwayat (siapa melakukan apa dan kapan)"), table] },
        init: form.start
      });
    }).catch(function (err) { toast(err.message, "error"); });
  }
  SE.openRequestDetail = openDetail;

  SE.register({
    id: "requests", title: "Pengajuan", icon: "wxi-pencil", order: 45,
    build: function () {
      list = SE.pagedList({
        id: "rq", url: "/api/v1/requests", params: params, rowHeight: 60,
        columns: [
          { id: "request_number", header: "Nomor", fillspace: 1.5, template: function (o) { return esc(o.request_number); } },
          { id: "submitted_at", header: "Diajukan", fillspace: 1.3, template: function (o) { return SE.dateTwoLine(o.submitted_at); } },
          { id: "product_name", header: "Produk", fillspace: 2.4, template: function (o) {
            return SE.twoLine(o.product_name, o.batch_number); } },
          { id: "request_type", header: "Jenis", fillspace: 1.9, template: function (o) {
            return SE.twoLine(SE.REQUEST_TYPE_LABEL[o.request_type], o.basis_label || "-"); } },
          { id: "quantity", header: "Jumlah", fillspace: 0.7, css: { "text-align": "right" }, template: function (o) { return esc(o.quantity); } },
          { id: "status", header: "Status", width: 130, template: function (o) { return SE.requestBadge(o.status); } },
          { id: "submitted_by_name", header: "Pengaju", fillspace: 1.2, template: function (o) { return esc(o.submitted_by_name); } },
          { id: "actions", header: "", width: 150, template: actionsCell }
        ],
        onRowClick: function (item) { openDetail(item.id); },
        onClick: {
          "act-approve": function (e, id) { decide(this.getItem(id), "approve"); return false; },
          "act-reject": function (e, id) { decide(this.getItem(id), "reject"); return false; },
          "act-cancel": function (e, id) { decide(this.getItem(id), "cancel"); return false; },
          "act-complete": function (e, id) { complete(this.getItem(id)); return false; }
        }
      });

      var buttons = [];
      if (SE.isStaff()) {
        buttons.push({ view: "button", value: "+ Ajukan", css: "webix_primary", width: 120,
          click: function () { SE.openRequestForm(null, null, function () { list.reload(true); }); } });
      }

      return SE.listPage({
        id: "requests", title: "Pengajuan Pengembalian / Pemusnahan",
        subtitle: "Untuk barang yang kritis, sudah kedaluwarsa, atau rusak. Harus disetujui Supervisor dulu; stok berkurang otomatis saat ditandai Selesai.",
        onShow: function () { list.reload(true); }, list: list, buttons: buttons,
        filters: [
          { view: "richselect", id: "rqStatus", value: "", options: [{ id: SE.ALL, value: "Semua status" }].concat(
            Object.keys(SE.REQUEST_STATUS_LABEL).map(function (k) { return { id: k, value: SE.REQUEST_STATUS_LABEL[k] }; })),
            on: { onChange: function () { list.reload(true); } } },
          { view: "richselect", id: "rqType", value: "", options: [{ id: SE.ALL, value: "Semua jenis" },
            { id: "disposal", value: "Pemusnahan" }, { id: "return", value: "Pengembalian" }],
            on: { onChange: function () { list.reload(true); } } }
        ]
      });
    }
  });
})();
