/* Keluar-Masuk Stok (SD 5.3 B, D): barang terjual dicatat PER PRODUK (misalnya rekap harian dari kasir, tanpa
   alasan). Sistem otomatis mengurangi stok dari kiriman yang paling cepat kedaluwarsa (FEFO), melewati barang
   Expired dan barang rusak. Juga riwayat semua pergerakan, yang tidak dapat diubah atau dihapus. */
(function () {
  "use strict";

  var esc = SE.esc, api = SE.api, toast = SE.toast;
  var list;

  var SOURCE_LABEL = { manual: "Dicatat langsung", csv_import: "Dari file", inspection: "Dari cek fisik", handling_request: "Dari pengajuan" };

  function params() {
    return { movement_type: $$("mType").getValue(), date_from: SE.dateOnly($$("mFrom").getValue()),
      date_to: SE.dateOnly($$("mTo").getValue()), sort: "-created_at" };
  }

  /* Barang terjual per produk. Pilih produk -> tampil stok yang bisa dijual dan batch yang akan dikurangi. */
  SE.openStockOutForm = function (onDone) {
    var requestId = SE.uuid();
    var batches = [];

    /* batch yang datang setelah tanggal penjualan tidak ikut (sama dengan aturan di server) */
    function usable() {
      var day = SE.dateOnly($$("soDate").getValue()) || SE.todayIso();
      return batches.filter(function (b) { return b.received_date <= day; });
    }

    function plan(qty) {
      var left = qty, parts = [];
      usable().forEach(function (b) {
        if (left <= 0) { return; }
        var take = Math.min(left, b.sellable_quantity);
        if (take > 0) { parts.push(b.batch_number + " (kedaluwarsa " + SE.fmtDate(b.expiry_date) + "): " + take); left -= take; }
      });
      return parts;
    }

    function showInfo() {
      var info = $$("soInfo");
      if (!info) { return; }
      var productId = $$("soProduct").getValue();
      if (!productId) { info.setHTML(""); return; }
      var total = usable().reduce(function (n, b) { return n + b.sellable_quantity; }, 0);
      var unit = batches.length ? batches[0].unit : "";
      if (!total) {
        info.setHTML("<span class='form-hint warn'>Produk ini tidak punya stok yang boleh dijual (habis, sudah kedaluwarsa, atau rusak).</span>");
        return;
      }
      var qty = Number($$("soQty").getValue()) || 0;
      var html = "Stok yang bisa dijual: <b>" + esc(total) + " " + esc(unit) + "</b>";
      if (qty > total) {
        html += "<br><span style='color:#b91c1c'>Jumlah terjual melebihi stok yang bisa dijual.</span>";
      } else if (qty > 0) {
        html += "<br>Stok akan dikurangi dari: " + plan(qty).map(esc).join("; ");
      }
      info.setHTML("<span class='form-hint'>" + html + "</span>");
    }

    function loadProduct(productId) {
      batches = [];
      showInfo();
      if (!productId) { return; }
      api("GET", "/api/v1/batches/fefo?product_id=" + encodeURIComponent(productId)).then(function (res) {
        batches = res.data;
        showInfo();
      }).catch(function (err) { toast(err.message, "error"); });
    }

    var win = SE.formWindow({ id: "winStockOut", title: "Catat Barang Terjual", width: 520, elements: [
      SE.tip("Isi total barang yang terjual, misalnya dari rekap kasir harian. Stok dikurangi otomatis dari kiriman " +
        "yang paling dekat kedaluwarsa."),
      { view: "combo", id: "soProduct", name: "product_id", label: "Produk", placeholder: "Ketik nama atau kode produk", options: [], value: "",
        on: { onChange: loadProduct } },
      { view: "datepicker", id: "soDate", name: "sale_date", label: "Tanggal penjualan (hari ini atau sampai 7 hari lalu)",
        format: "%Y-%m-%d", stringResult: true, value: SE.todayIso(), on: { onChange: showInfo } },
      { view: "text", id: "soQty", name: "quantity", label: "Jumlah terjual", type: "number",
        on: { onTimedKeyPress: showInfo, onChange: showInfo } },
      { view: "template", id: "soInfo", borderless: true, autoheight: true, template: "" },
      { view: "text", name: "notes", label: "Catatan (opsional)", placeholder: "Contoh: rekap kasir 14 November" },
      SE.note("Barang kedaluwarsa atau rusak tidak bisa dicatat terjual (untuk itu buat pengajuan). " +
        "Setelah disimpan, catatan ini tidak bisa diubah atau dihapus."),
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winStockOut").close(); } },
        { view: "button", value: "Simpan", css: "webix_primary", click: function () {
          var v = $$("winStockOutForm").getValues();
          var body = { product_id: v.product_id, quantity: v.quantity === "" ? "" : Number(v.quantity), notes: v.notes,
            sale_date: SE.dateOnly(v.sale_date), client_request_id: requestId };
          SE.busy(this, api("POST", "/api/v1/movements/stock-out", body)).then(function (res) {
            $$("winStockOut").close();
            var used = res.data.movements.map(function (m) { return m.batch_number + " (" + m.quantity + ")"; }).join(", ");
            toast("Penjualan tanggal " + SE.fmtDate(res.data.sale_date) + " sudah dicatat. Stok dikurangi dari kiriman " + used + ".");
            if (onDone) { onDone(); }
          }).catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ] });
    win.show();
    api("GET", "/api/v1/products?is_active=true&sort=name&limit=100").then(function (res) {
      var f = $$("soProduct");
      f.define("options", res.data.map(function (p) { return { id: p.id, value: p.sku + " - " + p.name }; }));
      f.refresh();
    }).catch(function (err) { toast(err.message, "error"); });
  };

  SE.register({
    id: "movements", title: "Keluar-Masuk Stok", icon: "wxi-sync", order: 30,
    build: function () {
      list = SE.pagedList({
        id: "mov", url: "/api/v1/movements", params: params, rowHeight: 60,
        columns: [
          { id: "created_at", header: "Waktu", fillspace: 1.4, template: function (o) { return SE.dateTwoLine(o.created_at); } },
          { id: "product_name", header: "Produk", fillspace: 2.6, template: function (o) {
            return SE.twoLine(o.product_name, o.sku + " · " + o.batch_number); } },
          { id: "movement_type", header: "Jenis", fillspace: 1.4, template: function (o) { return esc(SE.MOVEMENT_LABEL[o.movement_type]); } },
          { id: "quantity", header: "Jumlah", fillspace: 0.8, css: { "text-align": "right" },
            template: function (o) { return (SE.isIncrease(o.movement_type) ? "+" : "-") + esc(o.quantity); } },
          { id: "quantity_after", header: "Stok (sebelum → sesudah)", fillspace: 1.3, template: function (o) {
            return esc(o.quantity_before) + " &rarr; " + esc(o.quantity_after); } },
          { id: "source_type", header: "Keterangan", fillspace: 1.8, template: function (o) {
            var info = o.request_number || o.reason || o.notes || (o.movement_type === "stock_out" ? "Terjual" : "");
            return SE.twoLine(SOURCE_LABEL[o.source_type] || "-", info || "-"); } },
          { id: "created_by_name", header: "Oleh", fillspace: 1.2, template: function (o) { return esc(o.created_by_name); } }
        ]
      });

      var buttons = [];
      if (SE.isStaff()) {
        buttons.push({ view: "button", value: "Impor File", width: 120, click: function () {
          SE.openImport({ title: "Catat Penjualan Harian dari File", kind: "sales", onDone: function () { list.reload(true); },
            note: "Satu baris = satu produk, <b>total terjualnya</b> (misalnya dari rekap kasir), dan tanggal penjualan " +
              "(boleh dikosongkan = hari ini; paling lama 7 hari ke belakang). Stok dikurangi otomatis " +
              "dari kiriman yang paling cepat kedaluwarsa. File yang sama tidak bisa dimasukkan dua kali, supaya penjualan tidak tercatat ganda." });
        } });
        buttons.push({ view: "button", value: "+ Catat Terjual", css: "webix_primary", width: 150,
          click: function () { SE.openStockOutForm(function () { list.reload(true); }); } });
      }

      return SE.listPage({
        id: "movements", title: "Keluar-Masuk Stok",
        subtitle: "Semua catatan barang datang, terjual, dan stok yang disamakan. Catatan ini tidak bisa diubah atau dihapus.",
        onShow: function () { list.reload(true); }, list: list, buttons: buttons,
        filters: [
          { view: "richselect", id: "mType", value: "", placeholder: "Semua jenis",
            options: [{ id: "", value: "Semua jenis" }].concat(Object.keys(SE.MOVEMENT_LABEL).map(function (k) {
              return { id: k, value: SE.MOVEMENT_LABEL[k] }; })), on: { onChange: function () { list.reload(true); } } },
          { view: "datepicker", id: "mFrom", placeholder: "Dari tanggal", format: "%Y-%m-%d", stringResult: true,
            width: SE.isNarrow() ? 0 : 170, on: { onChange: function () { list.reload(true); } } },
          { view: "datepicker", id: "mTo", placeholder: "Sampai tanggal", format: "%Y-%m-%d", stringResult: true,
            width: SE.isNarrow() ? 0 : 170, on: { onChange: function () { list.reload(true); } } }
        ]
      });
    }
  });
})();
