/* Halaman detail bersama: breadcrumb di atas, lalu isi (biasanya berupa form).
   Dipakai Produk, Batch, Penanganan, Pengguna, dan Lokasi. Halaman detail adalah satu "sel" di multiview,
   isinya diganti setiap kali dibuka. Menu samping tetap menunjuk ke halaman induk. */
(function () {
  "use strict";

  var esc = SE.esc;
  var guard = null; // fungsi yang mengembalikan true bila ada perubahan form yang belum disimpan

  SE.detailCell = function () {
    return { id: "detailPage", rows: [{ id: "detailBody" }] };
  };

  function leave(parentId) {
    $$("pages").setValue(parentId); // halaman induk memuat ulang daftarnya sendiri (onViewShow)
  }

  /* Kembali ke daftar. Bila ada perubahan yang belum disimpan, tanyakan dulu. */
  SE.closeDetail = function (parentId) {
    if (guard && guard()) {
      webix.confirm({
        title: "Belum disimpan", text: "Ada perubahan yang belum disimpan. Tetap keluar dari halaman ini?",
        ok: "Keluar tanpa simpan", cancel: "Tetap di sini"
      }).then(function () { guard = null; leave(parentId); }).catch(function () { });
      return;
    }
    leave(parentId);
  };

  /* cfg: parentId, parentTitle, title, buttons (opsional), body (konfigurasi Webix), init (opsional) */
  SE.showDetail = function (cfg) {
    guard = null;
    var narrow = SE.isNarrow();
    var padX = SE.gutter();
    var crumbs = '<a class="crumb crumb-link" href="#" tabindex="0">' + esc(cfg.parentTitle) + "</a>" +
      '<span class="crumb-sep">&rsaquo;</span><span class="crumb-now">' + esc(cfg.title) + "</span>";

    webix.ui({
      id: "detailBody",
      rows: [
        { view: "template", id: "detailCrumbs", css: "crumb-bar", height: 46, borderless: true, template: crumbs,
          onClick: { "crumb-link": function () { SE.closeDetail(cfg.parentId); return false; } } },
        SE.pageHead(cfg.title, cfg.subtitle, cfg.buttons),
        { view: "scrollview", scroll: "y", borderless: true, body: { paddingX: padX, paddingY: 12, margin: 14, rows: [cfg.body] } }
      ]
    }, $$("detailPage"), $$("detailBody"));

    $$("pages").setValue("detailPage");
    if (cfg.init) { cfg.init(); }
  };

  /* Form detail. Field dikirim sebagai daftar baris; baris berupa array = berdampingan (layar lebar).
     Tombol Simpan dan Batalkan baru muncul setelah ada isian yang berubah, dan hanya untuk yang boleh mengubah.
     cfg: id, rows, canEdit, values (objek untuk setValues), onSave(values) -> Promise, afterSave() */
  SE.detailForm = function (cfg) {
    var narrow = SE.isNarrow();
    var formId = cfg.id, barId = cfg.id + "_bar";
    var FIELD_H = 66, GAP = 6, PAD = 16, BAR_H = 46;
    var snapshot = "";

    function prep(f) {
      var c = Object.assign({ height: FIELD_H }, f);
      if (!cfg.canEdit || f.locked) { c.readonly = true; }
      delete c.locked;
      return c;
    }

    var visualRows = 0;
    var elements = [];
    cfg.rows.forEach(function (row) {
      if (Array.isArray(row)) {
        var cells = row.map(prep);
        if (narrow) {
          cells.forEach(function (c) { elements.push(c); visualRows += 1; });
        } else {
          elements.push({ cols: cells, margin: 14, height: FIELD_H });
          visualRows += 1;
        }
      } else {
        elements.push(prep(row));
        visualRows += 1;
      }
    });

    function current() { return JSON.stringify($$(formId).getValues()); }
    function isDirty() { return current() !== snapshot; }
    function check() {
      if (!cfg.canEdit) { return; }
      if (isDirty()) { $$(barId).show(); } else { $$(barId).hide(); }
    }
    function reset() {
      $$(formId).setValues(cfg.values);
      snapshot = current();
      $$(barId).hide();
    }
    function save() {
      var values = $$(formId).getValues();
      cfg.onSave(values).then(function () {
        snapshot = current();
        $$(barId).hide();
        SE.toast("Perubahan disimpan.");
        if (cfg.afterSave) { cfg.afterSave(); }
      }).catch(function (err) { SE.toast(SE.formErrorText(err), "error"); });
    }

    if (cfg.canEdit) {
      elements.push({ id: barId, hidden: true, height: BAR_H, margin: 10, cols: [
        { view: "label", label: "Ada perubahan yang belum disimpan.", css: "dirty-note" },
        { view: "button", value: "Batal", width: 110, click: reset },
        { view: "button", value: "Simpan", css: "webix_primary", width: 110, click: save }
      ] });
    }

    var height = PAD * 2 + visualRows * FIELD_H + Math.max(visualRows - 1, 0) * GAP + (cfg.canEdit ? BAR_H + GAP : 0);
    var form = {
      view: "form", id: formId, css: "detail-card", padding: PAD, margin: GAP, height: height,
      elementsConfig: { labelPosition: "top" }, elements: elements
    };

    return {
      ui: form, /* form memenuhi lebar halaman */
      height: height,
      /* Panggil setelah halaman tampil: isi nilai, ambil keadaan awal, lalu pantau perubahan. */
      start: function () {
        var f = $$(formId);
        f.setValues(cfg.values);
        snapshot = current();
        if (!cfg.canEdit) { return; }
        guard = isDirty;
        Object.keys(f.elements).forEach(function (name) {
          var view = f.elements[name];
          view.attachEvent("onTimedKeyPress", check);
          view.attachEvent("onChange", check);
          /* Tempel (paste) atau input IME tidak selalu memicu event tombol, jadi pantau juga event "input" bawaan browser. */
          var node = view.getInputNode && view.getInputNode();
          if (node && node.addEventListener) { node.addEventListener("input", check); }
        });
      }
    };
  };

  /* Daftar ringkas (read-only) di bawah form, misalnya riwayat. Tinggi mengikuti jumlah baris. */
  SE.detailTable = function (id, columns, data) {
    var h = 24 + 2 + 46 + Math.max(data.length, 1) * 52 + 6;
    return {
      css: "card", padding: 12, height: h, rows: [
        SE.flatTable({ id: id, columns: columns.map(function (c) { return c.width ? c : Object.assign({ fillspace: 1 }, c); }),
          rowHeight: 52, data: data, scrollY: false, keepTable: true })
      ]
    };
  };

  SE.sectionTitle = function (text) {
    return { view: "template", template: esc(text), css: "section-title", borderless: true, height: 40 };
  };
})();
