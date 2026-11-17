/* Pemeriksaan Stok (SD 5.5 A, 5.3 C): Staff dan Supervisor mencatat hasil cek fisik. Pemeriksaan tidak mengubah
   stok. Bila ada selisih, Staff dapat langsung menyesuaikan stok dari hasil pemeriksaan itu (tanpa persetujuan,
   tetapi selalu tampil di pemberitahuan Supervisor dan Admin).
   Barang rusak dihitung per buah: hanya yang rusak yang harus ditangani, sisanya tetap boleh dijual.
   Tanggal di kemasan dicocokkan; bila berbeda, menjadi usulan koreksi yang diputuskan Supervisor lain. */
(function () {
  "use strict";

  var esc = SE.esc, api = SE.api, toast = SE.toast;
  var list;

  /* none = tidak ada selisih; stale = stok sudah berubah sejak pemeriksaan, perlu pemeriksaan ulang */
  var ADJ_LABEL = { none: "-", available: "Belum", adjusted: "Sudah", stale: "Cek ulang dulu" };

  function params() {
    var diff = $$("iDiff").getValue();
    return { fitness: $$("iFit").getValue(), has_difference: diff === "true" ? "true" : "",
      correction: diff === "pending" ? "pending" : "", sort: "-inspected_at" };
  }

  /* Penyesuaian stok dari satu pemeriksaan (hanya Staff). */
  SE.adjustFromInspection = function (inspection, onDone) {
    var diff = inspection.difference;
    var text = "Stok tercatat " + inspection.system_quantity + ", hasil hitung " + inspection.physical_quantity +
      ". Stok kiriman " + inspection.batch_number + " akan " + (diff < 0 ? "dikurangi " : "ditambah ") + Math.abs(diff) +
      " supaya sama dengan hasil hitung. Lanjutkan?";
    webix.confirm({ title: "Samakan stok", text: esc(text), ok: "Ya, samakan", cancel: "Batal" })
      .then(function () { return api("POST", "/api/v1/inspections/" + inspection.id + "/adjust", {}); })
      .then(function () {
        toast("Stok sudah disamakan dengan hasil hitung.");
        if (onDone) { onDone(); }
      }).catch(function (err) { if (err && err.message) { toast(err.message, "error"); } });
  };

  /* Supervisor memutuskan usulan koreksi tanggal kedaluwarsa. */
  SE.decideExpiryCorrection = function (inspection, approve, onDone) {
    var fix = inspection.expiry_correction;
    var text = "Kiriman " + inspection.batch_number + ": tanggal kedaluwarsa tercatat " + SE.fmtDate(fix.old_date) +
      ", tanggal di kemasan " + SE.fmtDate(fix.proposed_date) + ".<br>" + (approve
        ? "Tanggal kiriman akan diganti menjadi " + SE.fmtDate(fix.proposed_date) + ". Catatan (opsional):"
        : "Tanggal kiriman tetap " + SE.fmtDate(fix.old_date) + ". Alasan penolakan (wajib):");
    webix.prompt({ title: approve ? "Setujui koreksi tanggal" : "Tolak koreksi tanggal", text: text,
      ok: approve ? "Setujui" : "Tolak", cancel: "Kembali", input: { placeholder: "Catatan" } })
      .then(function (note) {
        return api("POST", "/api/v1/inspections/" + inspection.id + "/expiry-correction/" + (approve ? "approve" : "reject"),
          { note: note || "" });
      })
      .then(function () {
        toast(approve ? "Tanggal kedaluwarsa sudah dikoreksi." : "Usulan koreksi ditolak.");
        SE.refreshNotifications();
        if (onDone) { onDone(); }
      }).catch(function (err) { if (err && err.message) { toast(err.message, "error"); } });
  };

  function afterSave(inspection, onDone) {
    if (inspection.expiry_correction) {
      webix.alert({ title: "Usulan koreksi tanggal terkirim", text: esc("Tanggal di kemasan (" + SE.fmtDate(inspection.expiry_correction.proposed_date) +
        ") akan dipakai setelah disetujui Supervisor. Sampai saat itu, tanggal lama tetap berlaku.") });
    }
    if (inspection.difference !== 0 && SE.isStaff()) {
      SE.adjustFromInspection(inspection, onDone);
    } else if (inspection.difference !== 0) {
      webix.alert({ title: "Jumlahnya berbeda", text: esc("Hasil hitung berbeda " + inspection.difference + " dari catatan. Staff bisa " +
        "menyamakan stok dari halaman Pemeriksaan Stok.") });
    }
  }

  /* Bagian yang rusak -> kondisi produk dan kemasan yang disimpan server */
  var DAMAGE_PART = {
    product: { product_condition: "rusak", packaging_condition: "baik" },
    packaging: { product_condition: "baik", packaging_condition: "rusak" },
    both: { product_condition: "rusak", packaging_condition: "rusak" }
  };

  /* Urutan isian mengikuti yang dikerjakan di rak: hitung -> pisahkan yang rusak -> cocokkan tanggal -> catatan. */
  SE.openInspectionForm = function (batch, onDone) {
    var requestId = SE.uuid();  // satu ID untuk satu kali pengisian form (mencegah pemeriksaan tercatat dua kali)
    var current = null;         // batch yang sedang dicek

    /* Tampilkan isian tambahan sesuai jawaban, lalu beri tahu apakah catatan wajib diisi. */
    function update() {
      var form = $$("winInspectionForm");
      if (!form) { return; }
      var v = form.getValues();
      var hasDamage = $$("inHasDamage").getValue() === "yes";
      if (hasDamage) { $$("inDamagedBox").show(); } else { $$("inDamagedBox").hide(); }
      if (v.expiry_label === "different") { $$("inLabelDate").show(); } else { $$("inLabelDate").hide(); }

      var counted = v.physical_quantity === "" ? null : Number(v.physical_quantity);
      var countHint = "";
      if (current && counted !== null) {
        var diff = counted - current.current_quantity;
        countHint = diff === 0 ? "<span class='form-hint ok'>Sama dengan stok di aplikasi.</span>"
          : "<span class='form-hint warn'>Selisih " + (diff > 0 ? "+" : "") + diff + " dari stok di aplikasi (" +
            esc(current.current_quantity) + ").</span>";
      }
      $$("inCountCheck").setHTML(countHint);

      var reasons = [];
      if (current && counted !== null && counted !== current.current_quantity) { reasons.push("jumlahnya berbeda"); }
      if (hasDamage) { reasons.push("ada yang rusak"); }
      if (v.expiry_label === "different") { reasons.push("tanggalnya berbeda"); }
      $$("inNotesHint").setHTML(reasons.length
        ? "<span class='form-hint warn'>Catatan wajib diisi karena " + reasons.join(", ") + ".</span>"
        : "<span class='form-hint'>Boleh dikosongkan kalau semuanya cocok dan baik.</span>");
    }

    var picker = SE.batchPicker(batch, { mode: "stock", onBatch: function (b) {
      current = b;
      var label = $$("inLabel");
      if (label) {
        label.define("options", [{ id: "match", value: "Sama dengan catatan" + (b ? " (" + SE.fmtDate(b.expiry_date) + ")" : "") },
          { id: "different", value: "Berbeda dengan catatan" }]);
        label.refresh();
      }
      update();
    } });

    var win = SE.formWindow({ id: "winInspection", title: "Cek Fisik Barang", width: 520, elements: [
      SE.tip("Hitung semua barang dari kiriman ini di rak dan pisahkan yang rusak. " +
        "Cocokkan juga tanggal kedaluwarsanya dengan yang tertulis di kemasan.")
    ].concat(picker.elements, [
      { view: "text", name: "physical_quantity", label: "Jumlah hasil hitung", type: "number",
        placeholder: "Contoh: 12", on: { onTimedKeyPress: update, onChange: update } },
      SE.hint("Hitung semuanya, termasuk yang rusak.", "inCountHint"),
      { view: "template", id: "inCountCheck", borderless: true, autoheight: true, template: "" },

      { view: "richselect", id: "inHasDamage", label: "Ada barang yang rusak?", value: "no",
        options: [{ id: "no", value: "Tidak ada" }, { id: "yes", value: "Ada" }],
        on: { onChange: update } },
      { id: "inDamagedBox", hidden: true, rows: [
        { cols: [
          { view: "text", name: "damaged_quantity", label: "Jumlah yang rusak", type: "number", placeholder: "Contoh: 2" },
          { view: "richselect", id: "inDamagePart", label: "Bagian yang rusak", value: "packaging",
            options: [{ id: "packaging", value: "Kemasan" }, { id: "product", value: "Isi produk" },
              { id: "both", value: "Kemasan dan isi" }] }
        ], margin: 10 },
        SE.hint("Barang yang rusak dipisahkan dari rak. Hanya barang itu yang nanti diajukan pengembalian atau pemusnahan; " +
          "sisanya tetap boleh dijual.")
      ] },

      { view: "richselect", id: "inLabel", name: "expiry_label", label: "Tanggal kedaluwarsa di kemasan",
        value: "match", options: [{ id: "match", value: "Sama dengan catatan" }, { id: "different", value: "Berbeda dengan catatan" }],
        on: { onChange: update } },
      { view: "datepicker", id: "inLabelDate", name: "label_expiry_date", label: "Tanggal di kemasan",
        format: "%Y-%m-%d", stringResult: true, hidden: true, bottomPadding: 18,
        bottomLabel: "Tanggal ini berlaku setelah disetujui Supervisor." },

      { view: "text", name: "notes", label: "Catatan", placeholder: "Contoh: 2 cup penyok, sudah dipisah dari rak" },
      SE.hint("", "inNotesHint"),

      SE.note("Hasil cek tidak langsung mengubah stok. Kalau jumlahnya berbeda, setelah disimpan ada pilihan Samakan stok."),
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winInspection").close(); } },
        { view: "button", value: "Simpan", css: "webix_primary", click: function () {
          var v = $$("winInspectionForm").getValues();
          var damaged = $$("inHasDamage").getValue() === "yes";
          var part = DAMAGE_PART[damaged ? $$("inDamagePart").getValue() : ""] ||
            { product_condition: "baik", packaging_condition: "baik" };
          var body = { batch_id: batch ? batch.id : v.batch_id, physical_quantity: v.physical_quantity === "" ? "" : Number(v.physical_quantity),
            product_condition: part.product_condition, packaging_condition: part.packaging_condition,
            damaged_quantity: damaged ? (v.damaged_quantity === "" ? "" : Number(v.damaged_quantity)) : 0,
            expiry_label: v.expiry_label, label_expiry_date: v.expiry_label === "different" ? SE.dateOnly(v.label_expiry_date) : "",
            notes: v.notes, client_request_id: requestId };
          SE.busy(this, api("POST", "/api/v1/inspections", body)).then(function (res) {
            $$("winInspection").close();
            toast("Hasil cek fisik sudah dicatat.");
            if (onDone) { onDone(); }
            afterSave(res.data, onDone);
          }).catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ]) });
    win.show();
    picker.start();
    update();
  };

  function canDecide(o) {
    return SE.isSupervisor() && o.expiry_correction && o.expiry_correction.status === "pending" && o.inspected_by !== SE.me.id;
  }

  function actions(o) {
    var html = SE.isStaff() && o.adjustment_status === "available" ? "<span class='act act-adjust'>Samakan stok</span>" : "";
    if (canDecide(o)) {
      html += "<span class='act act-fix-ok'>Setujui tanggal</span><span class='act act-danger act-fix-no'>Tolak</span>";
    }
    return html;
  }

  function labelText(o) {
    var fix = o.expiry_correction;
    if (!fix) { return "Sesuai"; }
    return SE.fmtDate(fix.proposed_date) + " (" + SE.CORRECTION_LABEL[fix.status] + ")";
  }

  SE.register({
    id: "inspections", title: "Pemeriksaan Stok", icon: "wxi-check", order: 40,
    build: function () {
      list = SE.pagedList({
        id: "insp", url: "/api/v1/inspections", params: params, rowHeight: 60,
        columns: [
          { id: "inspected_at", header: "Waktu", fillspace: 1.1, template: function (o) { return SE.dateTwoLine(o.inspected_at); } },
          { id: "product_name", header: "Produk", fillspace: 2.1, template: function (o) {
            return SE.twoLine(o.product_name, o.sku + " · " + o.batch_number); } },
          { id: "physical_quantity", header: "Tercatat → Dihitung", fillspace: 1.4, template: function (o) {
            var d = o.difference ? " (" + (o.difference > 0 ? "+" : "") + o.difference + ")" : "";
            return esc(o.system_quantity) + " &rarr; " + esc(o.physical_quantity) + esc(d); } },
          { id: "is_fit", header: "Kondisi", width: 130, template: function (o) {
            return o.is_fit ? SE.fitnessBadge("fit") : SE.badge("fit-unfit", o.damaged_quantity + " rusak"); } },
          { id: "label", header: "Tgl. kemasan", fillspace: 1.3, template: function (o) {
            return SE.twoLine(labelText(o), o.expiry_correction ? "tercatat " + SE.fmtDate(o.expiry_correction.old_date) : "", true); } },
          { id: "adjustment_status", header: "Disamakan", fillspace: 1, template: function (o) { return esc(ADJ_LABEL[o.adjustment_status]); } },
          { id: "notes", header: "Catatan", fillspace: 1.7, template: function (o) {
            return "<div class='cell2'><div class='reason-text'>" + (esc(o.notes) || "-") + "</div></div>"; } },
          { id: "inspected_by_name", header: "Oleh", fillspace: 1.3, template: function (o) { return esc(o.inspected_by_name); } },
          { id: "actions", header: "", width: 170, template: actions }
        ],
        onRowClick: function (item) { SE.openBatchDetail(item.batch_id); },
        onClick: {
          "act-adjust": function (e, id) { SE.adjustFromInspection(this.getItem(id), function () { list.reload(); }); return false; },
          "act-fix-ok": function (e, id) { SE.decideExpiryCorrection(this.getItem(id), true, function () { list.reload(); }); return false; },
          "act-fix-no": function (e, id) { SE.decideExpiryCorrection(this.getItem(id), false, function () { list.reload(); }); return false; }
        }
      });

      var buttons = [];
      if (SE.isStaff() || SE.isSupervisor()) {
        buttons.push({ view: "button", value: "+ Cek Fisik", css: "webix_primary", width: 130,
          click: function () { SE.openInspectionForm(null, function () { list.reload(true); }); } });
      }

      return SE.listPage({
        id: "inspections", title: "Pemeriksaan Stok",
        subtitle: "Hasil hitung dan cek kondisi barang di rak toko. Kalau jumlahnya berbeda dengan catatan, Staff bisa menyamakan stoknya.",
        onShow: function () { list.reload(true); }, list: list, buttons: buttons,
        filters: [
          { view: "richselect", id: "iFit", value: "", options: [{ id: "", value: "Semua kondisi" }, { id: "fit", value: "Layak" },
            { id: "unfit", value: "Ada yang rusak" }], on: { onChange: function () { list.reload(true); } } },
          { view: "richselect", id: "iDiff", value: "", options: [{ id: "", value: "Semua" }, { id: "true", value: "Jumlahnya berbeda" },
            { id: "pending", value: "Koreksi tanggal menunggu" }], on: { onChange: function () { list.reload(true); } } }
        ]
      });
    }
  });
})();
