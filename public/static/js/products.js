/* Master Produk (SD 5.2): semua peran melihat; Supervisor dan Admin menambah, mengubah, menonaktifkan, menghapus
   (hanya produk yang belum punya batch), dan impor CSV. */
(function () {
  "use strict";

  var esc = SE.esc, api = SE.api, toast = SE.toast;
  var list;

  function params() {
    return { q: $$("pSearch").getValue().trim(), category: $$("pCategory").getValue(), is_active: $$("pActive").getValue(),
      sort: "sku" };
  }

  function loadCategories() {
    return api("GET", "/api/v1/products/categories").then(function (res) {
      var options = [{ id: SE.ALL, value: "Semua kategori" }].concat(res.data.map(function (c) { return { id: c, value: c }; }));
      var filter = $$("pCategory");
      var current = filter.getValue();
      filter.define("options", options);
      filter.refresh();
      filter.setValue(current || "");
    });
  }

  function onShow() { loadCategories().then(function () { list.reload(true); }); }

  function priceValue(v) { return v === "" || v == null ? "" : Number(String(v).replace(/[^\d]/g, "")); }

  function remove(p) {
    webix.confirm({ title: "Hapus produk", text: esc("Hapus produk " + p.sku + " - " + p.name + " secara permanen?"),
      ok: "Hapus", cancel: "Batal" }).then(function () {
      return api("DELETE", "/api/v1/products/" + p.id);
    }).then(function () {
      toast("Produk dihapus.");
      SE.closeDetail("products");
    }).catch(function (err) { if (err && err.message) { toast(err.message, "error"); } });
  }

  /* ---------- halaman detail ---------- */
  function openDetail(id) {
    api("GET", "/api/v1/products/" + id).then(function (res) {
      var p = res.data;
      var canEdit = SE.canManageProducts();
      var form = SE.detailForm({
        id: "pdForm", canEdit: canEdit,
        values: { sku: p.sku, is_active: p.is_active ? "true" : "false", name: p.name, category: p.category,
          unit: p.unit, price: String(p.price), min_stock: String(p.min_stock || 0), description: p.description || "",
          pack_unit: p.pack_unit || "", pack_size: p.pack_size ? String(p.pack_size) : "" },
        rows: [
          [{ view: "text", name: "sku", label: "Kode produk", locked: true },
            { view: "richselect", name: "is_active", label: "Status",
              options: [{ id: "true", value: "Aktif" }, { id: "false", value: "Nonaktif" }] }],
          { view: "text", name: "name", label: "Nama produk" },
          [{ view: "text", name: "category", label: "Kategori" }, { view: "text", name: "unit", label: "Satuan terkecil (yang dijual)" }],
          [{ view: "text", name: "pack_unit", label: "Satuan besar (opsional, misal karton)" },
            { view: "text", name: "pack_size", label: "Isi per satuan besar" }],
          [{ view: "text", name: "price", label: "Harga jual (Rp, tulis angka saja)" },
            { view: "text", name: "min_stock", label: "Stok minimum (0 = tidak dipantau)" }],
          { view: "text", name: "description", label: "Deskripsi (opsional)" }
        ],
        onSave: function (v) {
          return api("PUT", "/api/v1/products/" + p.id, { name: v.name, category: v.category, unit: v.unit,
            price: priceValue(v.price), pack_unit: v.pack_unit, pack_size: priceValue(v.pack_size), min_stock: priceValue(v.min_stock) === "" ? 0 : priceValue(v.min_stock),
            description: v.description, is_active: v.is_active === "true" });
        },
        afterSave: function () { loadCategories(); }
      });
      var buttons = [];
      if (canEdit && !p.has_batches) {
        buttons.push({ view: "button", value: "Hapus produk", css: "danger-btn", width: 140, click: function () { remove(p); } });
      }
      SE.showDetail({
        parentId: "products", parentTitle: "Data Produk", title: p.sku + " - " + p.name,
        subtitle: p.has_batches ? "Produk ini sudah pernah punya stok, jadi tidak bisa dihapus. Bila tidak dijual lagi, ubah statusnya menjadi Nonaktif." : "",
        buttons: buttons, body: form.ui, init: form.start
      });
    }).catch(function (err) { toast(err.message, "error"); });
  }

  /* ---------- tambah ---------- */
  function openForm() {
    var win = SE.formWindow({ id: "winProduct", title: "Tambah Produk", width: 460, elements: [
      SE.tip("Hanya untuk produk yang punya tanggal kedaluwarsa. Kode produk harus unik. Stok tidak diisi di sini; " +
        "stok bertambah saat Staff mencatat Barang Datang."),
      { view: "text", name: "sku", label: "Kode produk (contoh: P016)" },
      { view: "text", name: "name", label: "Nama produk" },
      { view: "text", name: "category", label: "Kategori" },
      { view: "text", name: "unit", label: "Satuan terkecil yang dijual (contoh: pcs, kotak, botol)" },
      { cols: [
        { view: "text", name: "pack_unit", label: "Satuan besar (opsional)", placeholder: "karton" },
        { view: "text", name: "pack_size", label: "Isinya", placeholder: "24" }
      ], margin: 10 },
      SE.note("Satuan besar hanya untuk memudahkan saat barang datang (misalnya 3 karton). Stok tetap dihitung dalam satuan terkecil."),
      { view: "text", name: "price", label: "Harga jual (Rp, tulis angka saja)" },
      { view: "text", name: "min_stock", label: "Stok minimum (0 = tidak dipantau)", value: "0" },
      SE.note("Stok minimum = batas untuk pesan ulang. Bila stok yang bisa dijual sama atau di bawah angka ini, produk " +
        "muncul di daftar <b>Stok menipis</b>."),
      { view: "text", name: "description", label: "Deskripsi (opsional)" },
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winProduct").close(); } },
        { view: "button", value: "Simpan", css: "webix_primary", click: function () {
          var v = $$("winProductForm").getValues();
          v.price = priceValue(v.price);
          v.pack_size = priceValue(v.pack_size);
          v.min_stock = priceValue(v.min_stock) === "" ? 0 : priceValue(v.min_stock);
          SE.busy(this, api("POST", "/api/v1/products", v)).then(function () {
            $$("winProduct").close();
            toast("Produk disimpan.");
            loadCategories();
            list.reload();
          }).catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ] });
    win.show();
  }

  SE.register({
    id: "products", title: "Data Produk", icon: "wxi-folder-open", order: 10,
    build: function () {
      list = SE.pagedList({
        id: "prod", url: "/api/v1/products", params: params,
        columns: [
          { id: "sku", header: "Kode", fillspace: 1, template: function (o) { return esc(o.sku); } },
          { id: "name", header: "Nama Produk", fillspace: 3.2, template: function (o) { return esc(o.name); } },
          { id: "category", header: "Kategori", fillspace: 1.8, template: function (o) { return esc(o.category); } },
          { id: "unit", header: "Satuan", fillspace: 1.1, template: function (o) {
            return o.pack_unit ? SE.twoLine(o.unit, "1 " + o.pack_unit + " = " + o.pack_size, true) : esc(o.unit); } },
          { id: "price", header: "Harga Jual", fillspace: 1.3, css: { "text-align": "right" },
            template: function (o) { return esc(SE.rupiah(o.price)); } },
          { id: "min_stock", header: "Stok min.", fillspace: 0.9, css: { "text-align": "right" },
            template: function (o) { return o.min_stock ? esc(o.min_stock) : "-"; } },
          { id: "is_active", header: "Status", width: 110, template: function (o) { return SE.activeBadge(o.is_active); } }
        ],
        onRowClick: function (item) { openDetail(item.id); }
      });

      var buttons = [];
      if (SE.canManageProducts()) {
        buttons.push({ view: "button", value: "Impor File", width: 120, click: function () {
          SE.openImport({ title: "Tambah Banyak Produk dari File", kind: "products", onDone: onShow });
        } });
        buttons.push({ view: "button", value: "+ Tambah Produk", css: "webix_primary", width: 150, click: openForm });
      }

      return SE.listPage({
        id: "products", title: "Data Produk",
        subtitle: SE.canManageProducts() ? "Daftar produk yang dijual. Klik salah satu untuk melihat atau mengubah." : "Daftar produk yang dijual.",
        buttons: buttons, onShow: onShow, list: list,
        filters: [
          { view: "search", id: "pSearch", placeholder: "Cari kode atau nama produk...",
            on: { onTimedKeyPress: function () { list.reload(true); } } },
          { view: "richselect", id: "pCategory", value: "", placeholder: "Semua kategori",
            options: [{ id: SE.ALL, value: "Semua kategori" }], on: { onChange: function () { list.reload(true); } } },
          { view: "richselect", id: "pActive", value: "", placeholder: "Semua status", width: SE.isNarrow() ? 0 : 170,
            options: [{ id: SE.ALL, value: "Semua status" }, { id: "true", value: "Aktif" }, { id: "false", value: "Nonaktif" }],
            on: { onChange: function () { list.reload(true); } } }
        ]
      });
    }
  });
})();
