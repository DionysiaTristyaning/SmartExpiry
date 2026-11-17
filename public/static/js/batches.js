/* Stok Barang (SD 5.3 A): daftar batch dengan status kedaluwarsa dan kelayakan, stok masuk (Staff) dengan
   layar konfirmasi, impor CSV stok awal (Staff), dan halaman detail berisi riwayat. Data batch tidak dapat diubah. */
(function () {
  "use strict";

  var esc = SE.esc, api = SE.api, toast = SE.toast;
  var list;

  function params() {
    return { q: $$("bSearch").getValue().trim(), status: $$("bStatus").getValue(), has_stock: $$("bStock").getValue(),
      sort: "expiry_date" };
  }

  /* ---------- stok masuk: isi -> konfirmasi -> simpan ---------- */
  SE.openStockInForm = function (onDone) {
    var requestId = SE.uuid();  // satu ID untuk satu kali pengisian form
    var products = {};

    /* Produk dengan satuan besar: isian karton + satuan kecil. Produk lain: satu isian jumlah. */
    function onProduct(id) {
      var p = products[id], packs = $$("siPacks"), qty = $$("siQty"), rej = $$("siRejected");
      if (!packs) { return; }
      if (p && p.pack_unit) {
        packs.define("label", "Jumlah " + p.pack_unit + " (isi " + p.pack_size + " " + p.unit + ")"); packs.refresh(); packs.show();
        qty.define("label", "Tambahan " + p.unit + " lepasan (bila ada)"); qty.refresh();
      } else {
        packs.setValue(""); packs.hide();
        qty.define("label", "Jumlah yang datang" + (p ? " (" + p.unit + ")" : "")); qty.refresh();
      }
      rej.define("label", "Jumlah ditolak" + (p ? " (" + p.unit + ")" : "")); rej.refresh();
    }

    var win = SE.formWindow({ id: "winStockIn", title: "Catat Barang Datang", width: 500, elements: [
      SE.tip("Barang dengan tanggal kedaluwarsa berbeda dicatat terpisah. Barang yang rusak saat datang boleh ditolak: " +
        "isi jumlah dan alasannya."),
      { view: "combo", id: "siProduct", name: "product_id", label: "Produk", placeholder: "Ketik nama atau kode produk", options: [],
        on: { onChange: onProduct } },
      { view: "text", id: "siPacks", name: "pack_quantity", label: "Jumlah karton", type: "number", hidden: true },
      { view: "text", id: "siQty", name: "quantity", label: "Jumlah yang datang", type: "number" },
      { cols: [
        { view: "text", id: "siRejected", name: "rejected_quantity", label: "Jumlah ditolak",
          type: "number", placeholder: "Isi 0 kalau tidak ada" },
        { view: "text", name: "reject_reason", label: "Alasan ditolak", placeholder: "Contoh: botol penyok" }
      ], margin: 10 },
      { view: "datepicker", name: "received_date", label: "Tanggal barang datang", format: "%Y-%m-%d", stringResult: true,
        value: SE.todayIso() },
      { view: "datepicker", name: "expiry_date", label: "Tanggal kedaluwarsa", format: "%Y-%m-%d", stringResult: true },
      { view: "text", name: "notes", label: "Catatan (opsional)" },
      SE.note("Disimpan sebagai <b>kiriman baru</b> dengan nomor otomatis. Barang yang ditolak tidak masuk stok, tetapi tetap tercatat. " +
        "Setelah disimpan, data ini <b>tidak bisa diubah</b>."),
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winStockIn").close(); } },
        { view: "button", value: "Lanjut", css: "webix_primary", click: function () {
          var body = values();
          SE.busy(this, api("POST", "/api/v1/batches/preview", body)).then(function (res) {
            confirmStep(body, res.data);
          }).catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ] });

    function values() {
      var v = $$("winStockInForm").getValues();
      var num = function (x) { return x === "" || x == null ? "" : Number(x); };
      return { product_id: v.product_id, quantity: num(v.quantity), pack_quantity: num(v.pack_quantity),
        rejected_quantity: num(v.rejected_quantity), reject_reason: v.reject_reason,
        received_date: SE.dateOnly(v.received_date), expiry_date: SE.dateOnly(v.expiry_date), notes: v.notes,
        client_request_id: requestId };
    }

    function confirmStep(body, p) {
      var text = "<div style='line-height:1.7'><b>" + esc(p.sku + " - " + p.product_name) + "</b><br>" +
        (p.pack ? "Datang: " + esc(p.pack.count) + " " + esc(p.pack.unit) + (p.pack.loose ? " + " + esc(p.pack.loose) + " " + esc(p.unit) : "") +
          " = <b>" + esc(p.received_quantity) + " " + esc(p.unit) + "</b><br>" : "Datang: <b>" + esc(p.received_quantity) + " " + esc(p.unit) + "</b><br>") +
        (p.rejected_quantity ? "Ditolak (rusak): <b>" + esc(p.rejected_quantity) + " " + esc(p.unit) + "</b> &middot; " + esc(p.reject_reason) + "<br>" : "") +
        (p.quantity ? "Masuk stok: <b>" + esc(p.quantity) + " " + esc(p.unit) + "</b><br>"
          : "<b style='color:#b91c1c'>Semua ditolak: tidak ada yang masuk stok.</b><br>") +
        "Tanggal datang: " + esc(SE.fmtDate(p.received_date)) + "<br>" +
        "Kedaluwarsa: <b>" + esc(SE.fmtDate(p.expiry_date)) + "</b> (" + esc(SE.daysText(p)) + ") " + SE.statusBadge(p.expiry_status) +
        "<br><br>Sudah benar? Setelah disimpan, data ini tidak bisa diubah.</div>";
      webix.confirm({ title: "Cek Sebelum Simpan", text: text, ok: "Ya, Simpan", cancel: "Ubah lagi",
        width: Math.min(440, window.innerWidth - 20) })
        .then(function () { return api("POST", "/api/v1/batches", body); })
        .then(function (res) {
          $$("winStockIn").close();
          toast(res.data.rejected_all ? "Penolakan barang sudah dicatat. Tidak ada stok yang masuk."
            : "Barang datang sudah dicatat dengan nomor kiriman " + res.data.batch_number + ".");
          if (onDone) { onDone(); }
        }).catch(function (err) { if (err && err.message) { toast(SE.formErrorText(err), "error"); } });
    }

    win.show();
    api("GET", "/api/v1/products?is_active=true&sort=name&limit=100").then(function (res) {
      var f = $$("siProduct");
      res.data.forEach(function (p) { products[p.id] = p; });
      f.define("options", res.data.map(function (p) { return { id: p.id, value: p.sku + " - " + p.name }; }));
      f.refresh();
    }).catch(function (err) { toast(err.message, "error"); });
  };

  /* ---------- halaman detail ---------- */
  function table(id, columns, rows) {
    return SE.detailTable(id, columns.map(function (c) { c.template = "#" + c.id + "#"; return c; }),
      rows.map(function (r) { Object.keys(r).forEach(function (k) { r[k] = esc(r[k]); }); return r; }));
  }

  function openDetail(id) {
    api("GET", "/api/v1/batches/" + id).then(function (res) {
      var b = res.data;
      var reopen = function () { openDetail(b.id); };
      var last = b.last_inspection;
      var form = SE.detailForm({
        id: "bdForm", canEdit: false,
        values: {
          product: b.sku + " - " + b.product_name, batch_number: b.batch_number,
          received_date: SE.fmtDate(b.received_date),
          expiry_date: SE.fmtDate(b.expiry_date) + ((b.expiry_history || []).length
            ? " (dikoreksi dari " + SE.fmtDate(b.expiry_history[b.expiry_history.length - 1].old_date) + ")" : ""),
          status: SE.STATUS_LABEL[b.expiry_status] + " (" + SE.daysText(b) + ")",
          /* tanggal pemeriksaan hanya ditulis bila kerusakannya memang hasil Cek Fisik (bukan laporan yang sedang ditahan) */
          fitness: SE.FITNESS_LABEL[b.fitness] +
            (last && (b.recorded_damaged_quantity || !b.held_quantity) ? " (pemeriksaan " + SE.fmtDateTime(last.inspected_at) + ")" : "") +
            (b.held_quantity ? " (" + b.held_quantity + " ditahan karena pengajuan barang rusak)" : "") +
            (b.check_due ? " · perlu dicek lagi" : ""),
          initial_quantity: b.initial_quantity + " " + b.unit + (b.rejected_quantity
            ? " (datang " + b.received_quantity + ", ditolak " + b.rejected_quantity + ": " + b.reject_reason + ")" : "") +
            (b.pack ? " · " + b.pack.count + " " + b.pack.unit + (b.pack.loose ? " + " + b.pack.loose : "") : ""),
          current_quantity: b.current_quantity + " " + b.unit + (b.damaged_quantity
            ? " (" + b.damaged_quantity + " rusak, " + b.sellable_quantity + " bisa dijual)" : ""),
          created_by: b.created_by_name + " (" + SE.fmtDateTime(b.created_at) + ")"
        },
        rows: [
          [{ view: "text", name: "product", label: "Produk" }, { view: "text", name: "batch_number", label: "Nomor kiriman" }],
          [{ view: "text", name: "received_date", label: "Tanggal datang" }, { view: "text", name: "expiry_date", label: "Tanggal kedaluwarsa" }],
          [{ view: "text", name: "status", label: "Status kedaluwarsa" }, { view: "text", name: "fitness", label: "Kondisi barang" }],
          [{ view: "text", name: "initial_quantity", label: "Jumlah masuk stok saat datang" },
            { view: "text", name: "current_quantity", label: "Sisa stok sekarang" }],
          { view: "text", name: "created_by", label: "Dicatat oleh" }
        ]
      });

      var moves = table("bdMoves", [
        { id: "at", header: "Tanggal", width: 160 }, { id: "type", header: "Jenis", width: 140 },
        { id: "qty", header: "Jumlah", width: 80 }, { id: "stock", header: "Stok (sebelum → sesudah)", width: 180 },
        { id: "by", header: "Dicatat oleh", width: 150 }, { id: "info", header: "Keterangan", fillspace: true, minWidth: 180 }
      ], (b.movements || []).map(function (m) {
        return { at: SE.fmtDateTime(m.created_at), type: SE.MOVEMENT_LABEL[m.movement_type],
          qty: (SE.isIncrease(m.movement_type) ? "+" : "-") + m.quantity, stock: m.quantity_before + " → " + m.quantity_after,
          by: m.created_by_name, info: m.reason || m.notes || (m.movement_type === "stock_out" ? "Terjual" : "") };
      }));
      var insp = table("bdInsp", [
        { id: "at", header: "Waktu", width: 160 }, { id: "qty", header: "Tercatat → Dihitung", width: 160 },
        { id: "cond", header: "Produk / Kemasan", width: 150 }, { id: "damaged", header: "Rusak", width: 70 },
        { id: "label", header: "Tanggal di kemasan", width: 200 }, { id: "by", header: "Oleh", width: 130 },
        { id: "notes", header: "Catatan", fillspace: true, minWidth: 180 }
      ], (b.inspections || []).map(function (i) {
        var fix = i.expiry_correction;
        return { at: SE.fmtDateTime(i.inspected_at), qty: i.system_quantity + " → " + i.physical_quantity,
          cond: SE.CONDITION_LABEL[i.product_condition] + " / " + SE.CONDITION_LABEL[i.packaging_condition],
          damaged: i.damaged_quantity != null ? i.damaged_quantity : (i.is_fit ? 0 : i.physical_quantity),
          label: fix ? SE.fmtDate(fix.proposed_date) + " (" + SE.CORRECTION_LABEL[fix.status] + ")" : "Sesuai",
          by: i.inspected_by_name, notes: i.notes || "-" };
      }));
      var reqs = table("bdReq", [
        { id: "no", header: "Nomor", width: 150 }, { id: "type", header: "Jenis", width: 230 },
        { id: "qty", header: "Jumlah", width: 80 }, { id: "status", header: "Status", width: 120 },
        { id: "by", header: "Pengaju", fillspace: true, minWidth: 150 }
      ], (b.requests || []).map(function (r) {
        return { no: r.request_number,
          type: SE.REQUEST_TYPE_LABEL[r.request_type] + (r.basis ? " · " + SE.BASIS_LABEL[r.basis] : ""), qty: r.quantity,
          status: SE.REQUEST_STATUS_LABEL[r.status], by: r.submitted_by_name };
      }));

      var buttons = [];
      if (SE.isStaff() || SE.isSupervisor()) {
        buttons.push({ view: "button", value: "Cek fisik", width: 110, click: function () { SE.openInspectionForm(b, reopen); } });
      }
      /* Barang terjual dicatat per produk di halaman Keluar-Masuk Stok (sistem memilih batch otomatis). */
      if (SE.isStaff() && b.current_quantity > 0) {
        if (SE.requestable(b).length) {  // hanya barang Expired, rusak, atau batch Near Expired/Critical yang belum diajukan
          buttons.push({ view: "button", value: "Ajukan pengembalian/pemusnahan", css: "webix_primary", width: 200,
            click: function () { SE.openRequestForm(b, null, reopen); } });
        } else if ((b.open_requests || []).length) {
          buttons.push({ view: "label", width: 260, css: "form-hint",
            label: "Sudah diajukan: " + esc(SE.openRequestText(b)) });
        }
      }

      SE.showDetail({
        parentId: "batches", parentTitle: "Stok Barang", title: b.batch_number + " · " + b.product_name,
        buttons: buttons,
        body: { rows: [form.ui, SE.sectionTitle("Riwayat keluar-masuk stok"), moves, SE.sectionTitle("Riwayat cek fisik"),
          insp, SE.sectionTitle("Riwayat pengajuan"), reqs] },
        init: form.start
      });
    }).catch(function (err) { toast(err.message, "error"); });
  }
  SE.openBatchDetail = openDetail;

  SE.register({
    id: "batches", title: "Stok Barang", icon: "wxi-file", order: 20,
    build: function () {
      list = SE.pagedList({
        id: "batch", url: "/api/v1/batches", params: params, rowHeight: 60,
        columns: [
          { id: "batch_number", header: "Kiriman", fillspace: 1.4, template: function (o) { return esc(o.batch_number); } },
          { id: "product_name", header: "Produk", fillspace: 2.6, template: function (o) { return SE.twoLine(o.product_name, o.sku); } },
          { id: "expiry_date", header: "Kedaluwarsa", fillspace: 1.6, template: function (o) { return SE.twoLine(SE.fmtDate(o.expiry_date), SE.daysText(o), true); } },
          { id: "expiry_status", header: "Status", width: 165, template: function (o) { return SE.statusBadge(o.expiry_status); } },
          { id: "current_quantity", header: "Sisa / Awal", fillspace: 0.8, css: { "text-align": "right" },
            template: function (o) { return esc(o.current_quantity) + " / " + esc(o.initial_quantity); } },
          { id: "fitness", header: "Kondisi", width: 215, template: function (o) {
            return SE.fitnessBadge(o.fitness) + (o.damaged_quantity ? " <small>" + esc(o.damaged_quantity) + " rusak</small>" : ""); } }
        ],
        onRowClick: function (item) { openDetail(item.id); }
      });

      var buttons = [];
      if (SE.isStaff()) {
        buttons.push({ view: "button", value: "Impor File", width: 120, click: function () {
          SE.openImport({ title: "Catat Banyak Stok dari File", kind: "stock", onDone: function () { list.reload(true); },
            note: "Setiap baris dicatat sebagai satu kiriman baru. File yang sama tidak bisa dimasukkan dua kali, supaya stok tidak tercatat ganda." });
        } });
        buttons.push({ view: "button", value: "+ Barang Datang", css: "webix_primary", width: 150,
          click: function () { SE.openStockInForm(function () { list.reload(true); }); } });
      }

      return SE.listPage({
        id: "batches", title: "Stok Barang",
        subtitle: "Setiap kali barang datang dicatat sebagai satu kiriman. Klik salah satu untuk melihat rincian dan riwayatnya.",
        onShow: function () { list.reload(true); }, list: list, buttons: buttons,
        filters: [
          { view: "search", id: "bSearch", placeholder: "Cari nomor kiriman, kode, atau nama produk...",
            on: { onTimedKeyPress: function () { list.reload(true); } } },
          { view: "richselect", id: "bStatus", value: "", placeholder: "Semua status", width: SE.isNarrow() ? 0 : 180,
            options: [{ id: SE.ALL, value: "Semua status" }].concat(
              SE.STATUS_ORDER.map(function (s) { return { id: s, value: SE.STATUS_LABEL[s] }; })),
            on: { onChange: function () { list.reload(true); } } },
          { view: "richselect", id: "bStock", value: "true", width: SE.isNarrow() ? 0 : 180,
            options: [{ id: "true", value: "Yang masih ada stok" }, { id: SE.ALL, value: "Semua, termasuk yang habis" }],
            on: { onChange: function () { list.reload(true); } } }
        ]
      });
    }
  });
})();
