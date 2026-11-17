/* Pembantu bersama untuk semua halaman (Webix). Semua teks dari server di-escape sebelum ditampilkan. */
(function () {
  "use strict";

  var SE = window.SE = { me: null, modules: [] };

  SE.csrf = document.querySelector('meta[name="csrf-token"]').getAttribute("content");

  /* Penanda pilihan "Semua ..." pada filter. Webix tidak menerima id kosong (diganti nomor acak), jadi dipakai penanda
     tetap ini; SE.query dan SE.go mengubahnya kembali menjadi "tanpa filter". */
  SE.ALL = "__all__";

  SE.ROLE_LABEL = { admin: "Admin", supervisor: "Supervisor", staff: "Staff" };
  SE.STATUS_LABEL = {
    normal: "Aman", monitoring: "Dipantau", near_expired: "Hampir Kedaluwarsa",
    critical: "Kritis", expired: "Kedaluwarsa"
  };
  SE.STATUS_ORDER = ["normal", "monitoring", "near_expired", "critical", "expired"];
  SE.MOVEMENT_LABEL = {
    stock_in: "Stok Masuk", stock_out: "Stok Keluar",
    adjustment_in: "Stok disamakan (tambah)", adjustment_out: "Stok disamakan (kurang)"
  };
  SE.CONDITION_LABEL = { baik: "Baik", rusak: "Rusak" };
  SE.FITNESS_LABEL = { fit: "Layak", partial: "Sebagian rusak", unfit: "Tidak layak", unchecked: "Belum diperiksa" };
  SE.BASIS_LABEL = { expired: "Barang kedaluwarsa", damaged: "Barang rusak", near_expiry: "Mendekati kedaluwarsa (masih bagus)" };
  SE.REQUEST_TYPE_LABEL = { "return": "Pengembalian", disposal: "Pemusnahan" };
  SE.CORRECTION_LABEL = { pending: "menunggu Supervisor", approved: "disetujui", rejected: "ditolak" };
  SE.REQUEST_STATUS_LABEL = {
    pending: "Menunggu", approved: "Disetujui", rejected: "Ditolak", completed: "Selesai", cancelled: "Dibatalkan"
  };

  /* ---------- peran ---------- */
  SE.isStaff = function () { return SE.me && SE.me.role === "staff"; };
  SE.isSupervisor = function () { return SE.me && SE.me.role === "supervisor"; };
  SE.isAdmin = function () { return SE.me && SE.me.role === "admin"; };
  SE.canManageProducts = function () { return SE.isSupervisor() || SE.isAdmin(); };

  /* ---------- teks aman ---------- */
  SE.esc = function (value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  SE.rupiah = function (n) {
    if (n == null || n === "") { return "-"; }
    return "Rp " + Number(n).toLocaleString("id-ID");
  };

  /* ID unik untuk satu kali pengisian form. Server menolak kiriman kedua dengan ID yang sama (mencegah stok
     tercatat dua kali karena klik ganda atau jaringan lambat). */
  SE.uuid = function () {
    if (window.crypto && window.crypto.randomUUID) { return window.crypto.randomUUID(); }
    var b = new Uint8Array(16);
    window.crypto.getRandomValues(b);
    b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  };

  /* ---------- komunikasi dengan server ---------- */
  function handle(res) {
    return res.json().catch(function () { return {}; }).then(function (json) {
      if (res.status === 401) {
        /* pesan (misalnya sesi berakhir karena tidak aktif) ditampilkan di halaman login */
        try { sessionStorage.setItem("loginNotice", (json.error && json.error.message) || ""); } catch (e) { }
        window.location.href = "/login";
      }
      if (!res.ok) {
        var err = new Error((json.error && json.error.message) || "Ada masalah. Coba lagi.");
        err.fields = (json.error && json.error.fields) || {};
        err.status = res.status;
        throw err;
      }
      return json;
    });
  }

  /* background = true: permintaan otomatis (misalnya cek lonceng tiap menit) yang TIDAK dihitung sebagai aktivitas,
     supaya sesi tetap berakhir bila pengguna meninggalkan komputer. */
  SE.api = function (method, url, body, background) {
    var options = {
      method: method, credentials: "same-origin",
      headers: { "X-CSRFToken": SE.csrf, "Accept": "application/json" }
    };
    if (background) { options.headers["X-Background"] = "1"; }
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(url, options).then(handle);
  };

  SE.upload = function (url, file) {
    var form = new FormData();
    form.append("file", file);
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": SE.csrf, "Accept": "application/json" }, body: form
    }).then(handle).then(function (json) { return json.data; });
  };

  /* Tombol simpan dikunci selama permintaan berjalan (mencegah klik ganda). */
  SE.busy = function (button, promise) {
    if (button && button.disable) { button.disable(); }
    return promise.then(function (v) { if (button && button.$view) { button.enable(); } return v; },
      function (e) { if (button && button.$view) { button.enable(); } throw e; });
  };

  /* ---------- tampilan kecil ---------- */
  SE.toast = function (text, type) {
    webix.message({ text: SE.esc(text), type: type || "success", expire: 4000 });
  };

  /* Pesan utama sudah menjelaskan isian yang salah. Keterangan per isian hanya ditambahkan bila ada lebih
     dari satu isian yang salah, supaya kalimatnya tidak berulang. */
  SE.formErrorText = function (err) {
    var parts = Object.keys(err.fields || {}).filter(function (k) { return k !== "client_request_id"; })
      .map(function (k) { return err.fields[k]; });
    return parts.length > 1 ? err.message + " (" + parts.join("; ") + ")" : err.message;
  };

  SE.badge = function (cls, text) { return '<span class="badge ' + cls + '">' + SE.esc(text) + "</span>"; };
  SE.activeBadge = function (active) {
    return active ? SE.badge("badge-ok", "Aktif") : SE.badge("badge-off", "Nonaktif");
  };
  SE.statusBadge = function (status) { return SE.badge("st-" + status, SE.STATUS_LABEL[status] || status); };
  SE.fitnessBadge = function (fitness) { return SE.badge("fit-" + fitness, SE.FITNESS_LABEL[fitness] || fitness); };
  SE.requestBadge = function (status) { return SE.badge("rq-" + status, SE.REQUEST_STATUS_LABEL[status] || status); };

  /* Datepicker Webix bisa mengembalikan "2026-10-12 00:00:00"; server hanya menerima "YYYY-MM-DD". */
  SE.dateOnly = function (value) {
    if (value instanceof Date) { return webix.Date.dateToStr("%Y-%m-%d")(value); }
    return String(value || "").slice(0, 10);
  };
  /* Tanggal "YYYY-MM-DD" ditampilkan sebagai "13 Nov 2026" (seragam di seluruh layar). */
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
  SE.fmtDate = function (iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    return m ? Number(m[3]) + " " + MONTHS[Number(m[2]) - 1] + " " + m[1] : (iso || "-");
  };
  SE.todayIso = function () {
    return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Jakarta" });
  };

  SE.twoLine = function (main, sub, plain) {
    return '<div class="cell2' + (plain ? " plain" : "") + '"><span>' + SE.esc(main) + "</span><small>" + SE.esc(sub) + "</small></div>";
  };

  SE.dateTwoLine = function (iso) {
    var t = SE.fmtDateTime(iso);
    if (t === "-") { return "-"; }
    var i = t.lastIndexOf(", ");
    return i < 0 ? SE.esc(t) : SE.twoLine(t.slice(0, i), t.slice(i + 2), true);
  };

  SE.isNarrow = function () { return window.innerWidth < 760; };
  /* Tablet / jendela setengah layar: kartu daftar masih berbentuk tabel, tetapi menu samping dan bilah atas diperkecil. */
  SE.isCompact = function () { return window.innerWidth < 1100; };
  /* phone < 760, tablet < 1000, desktop: tampilan disusun ulang bila ukuran jendela berpindah kelompok. */
  SE.layoutMode = function () { return SE.isNarrow() ? "phone" : SE.isCompact() ? "tablet" : "desktop"; };

  /* Waktu dari server (UTC) ditampilkan dalam zona waktu Jakarta. */
  SE.fmtDateTime = function (iso) {
    if (!iso) { return "-"; }
    try {
      return new Date(iso).toLocaleString("id-ID", {
        timeZone: "Asia/Jakarta", day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit", hour12: false
      });
    } catch (e) {
      return String(iso).slice(0, 16).replace("T", " ");
    }
  };

  SE.isIncrease = function (type) { return type === "stock_in" || type === "adjustment_in"; };

  /* Sisa 0 hari = Expired (tidak boleh dijual pada tanggal kedaluwarsanya). */
  SE.daysText = function (o) {
    if (o.remaining_days < 0) { return "lewat " + Math.abs(o.remaining_days) + " hari"; }
    if (o.remaining_days === 0) { return "kedaluwarsa hari ini"; }
    return "sisa " + o.remaining_days + " hari";
  };

  SE.batchLabel = function (b) {
    var damaged = b.damaged_quantity ? ", " + b.damaged_quantity + " rusak" : "";
    return b.batch_number + " (stok " + b.current_quantity + damaged + ", kedaluwarsa " + SE.fmtDate(b.expiry_date) + ")";
  };

  /* Pilihan Produk lalu Batch untuk form. Jika `batch` diberikan, keduanya sudah terpilih dan terkunci.
     opts.mode: "fefo" = hanya batch layak jual, urut FEFO, batch pertama dipilih otomatis (stok keluar);
                "stock" = semua batch yang masih berstok. */
  SE.batchPicker = function (batch, opts) {
    opts = opts || {};
    var onBatch = opts.onBatch || function () { };
    var cache = {};

    function batchOption(b, i) {
      var tag = opts.mode === "fefo" && i === 0 ? " ← jual duluan" : "";
      return { id: b.id, value: SE.batchLabel(b) + tag };
    }

    function loadBatches(productId) {
      var field = $$("pkBatch");
      field.define("options", []); field.refresh(); field.setValue("");
      onBatch(null);
      if (!productId) { return; }
      var url = opts.mode === "fefo"
        ? "/api/v1/batches/fefo?product_id=" + encodeURIComponent(productId)
        : "/api/v1/batches?has_stock=true&limit=100&sort=expiry_date&product_id=" + encodeURIComponent(productId);
      SE.api("GET", url).then(function (res) {
        var items = opts.filter ? res.data.filter(opts.filter) : res.data;  // opts.filter: batasi pilihan batch
        cache = {};
        items.forEach(function (b) { cache[b.id] = b; });
        field.define("options", items.map(batchOption));
        field.refresh();
        if (!items.length) {
          $$("pkHint").setHTML("<span class='form-hint warn'>" + SE.esc(opts.emptyText || (opts.mode === "fefo"
            ? "Produk ini tidak punya stok yang boleh dijual (habis, sudah kedaluwarsa, atau rusak)."
            : "Produk ini tidak punya stok.")) + "</span>");
        } else {
          $$("pkHint").setHTML(opts.mode === "fefo"
            ? "<span class='form-hint'>Yang dipilih otomatis adalah kiriman yang paling cepat kedaluwarsa, supaya dijual duluan. Boleh diganti.</span>" : "");
          if (opts.mode === "fefo") { field.setValue(res.data[0].id); }
        }
      }).catch(function (err) { SE.toast(err.message, "error"); });
    }

    /* Dibuka dari satu baris/kiriman: produk dan kiriman sudah pasti, jadi hanya ditampilkan (tidak ada pilihan). */
    if (batch) {
      return {
        elements: [
          { view: "text", id: "pkProduct", label: "Produk", value: batch.sku + " - " + batch.product_name, readonly: true },
          { view: "text", id: "pkBatchShown", label: "Kiriman", value: SE.batchLabel(batch), readonly: true },
          { view: "text", id: "pkBatch", name: "batch_id", value: batch.id, hidden: true },
          { view: "template", id: "pkHint", borderless: true, autoheight: true, template: "" }
        ],
        start: function () { onBatch(batch); }
      };
    }

    /* opts.productSource = "requestable": dropdown memuat SEMUA produk yang punya stok (staff boleh melaporkan barang
       rusak dari produk mana pun). Produk yang perlu ditangani diberi keterangan alasannya (kedaluwarsa, ada yang
       rusak, hampir kedaluwarsa) dan diurutkan paling atas; produk yang sehat ada di bawah tanpa keterangan. */
    var REQUEST_TAGS = ["kedaluwarsa", "ada yang rusak", "hampir kedaluwarsa"];
    var TAG_OF_BASIS = { expired: REQUEST_TAGS[0], damaged: REQUEST_TAGS[1], near_expiry: REQUEST_TAGS[2] };

    function allStockedBatches(page, acc) {
      return SE.api("GET", "/api/v1/batches?has_stock=true&limit=100&sort=expiry_date&page=" + page).then(function (res) {
        acc = acc.concat(res.data);
        return acc.length < (res.total || 0) && page < 10 ? allStockedBatches(page + 1, acc) : acc;
      });
    }

    function requestableProducts() {
      return allStockedBatches(1, []).then(function (batches) {
        var byProduct = {}, order = [];
        batches.forEach(function (b) {
          var options = SE.requestable(b);
          if (!options.length) { return; }
          if (!byProduct[b.product_id]) {
            byProduct[b.product_id] = { id: b.product_id, label: b.sku + " - " + b.product_name, tags: [] };
            order.push(byProduct[b.product_id]);
          }
          options.forEach(function (o) {
            if (o.direct) { return; }  // lapor rusak langsung selalu tersedia, jadi bukan alasan khusus
            var tag = TAG_OF_BASIS[o.basis];
            if (byProduct[b.product_id].tags.indexOf(tag) < 0) { byProduct[b.product_id].tags.push(tag); }
          });
        });
        order.forEach(function (p) {
          p.tags.sort(function (a, c) { return REQUEST_TAGS.indexOf(a) - REQUEST_TAGS.indexOf(c); });
          p.rank = p.tags.length ? REQUEST_TAGS.indexOf(p.tags[0]) : REQUEST_TAGS.length;  // tanpa keterangan: paling bawah
        });
        order.sort(function (a, c) { return a.rank - c.rank || a.label.localeCompare(c.label); });  // yang paling mendesak di atas
        return order.map(function (p) {
          return { id: p.id, value: p.tags.length ? p.label + " (" + p.tags.join(", ") + ")" : p.label };
        });
      });
    }

    function allProducts() {
      return SE.api("GET", "/api/v1/products?is_active=true&sort=name&limit=100").then(function (res) {
        return res.data.map(function (p) { return { id: p.id, value: p.sku + " - " + p.name }; });
      });
    }

    var requestable = opts.productSource === "requestable";
    return {
      elements: [
        { view: "combo", id: "pkProduct", label: "Produk",
          placeholder: requestable ? "Pilih produk (yang perlu ditangani ada di atas)" : "Ketik nama atau kode produk", options: [], value: "",
          on: { onChange: loadBatches } },
        { view: "richselect", id: "pkBatch", name: "batch_id", label: "Kiriman", options: [], value: "",
          on: { onChange: function (id) { onBatch(cache[id] || null); } } },
        { view: "template", id: "pkHint", borderless: true, autoheight: true, template: "" }
      ],
      start: function () {
        (requestable ? requestableProducts() : allProducts()).then(function (options) {
          var f = $$("pkProduct");
          if (!f) { return; }
          f.define("options", options);
          f.refresh();
          if (requestable && !options.length) {
            $$("pkHint").setHTML("<span class='form-hint'>Saat ini tidak ada barang yang perlu diajukan.</span>");
          }
        }).catch(function (err) { SE.toast(err.message, "error"); });
      }
    };
  };

  /* ---------- ekspor Excel (halaman Laporan) ---------- */
  SE.download = function (url) {
    return fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } }).then(function (res) {
      if (res.status === 401) { window.location.href = "/login"; throw new Error("Anda sudah keluar. Silakan masuk lagi."); }
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (json) {
          throw new Error((json.error && json.error.message) || "Gagal mengunduh file.");
        });
      }
      var match = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "");
      var name = match ? match[1] : "laporan.xlsx";
      return res.blob().then(function (blob) {
        var link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = name;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(function () { URL.revokeObjectURL(link.href); }, 2000);
        return name;
      });
    });
  };

  SE.query = function (params) {
    return Object.keys(params || {}).filter(function (k) { return params[k] !== "" && params[k] != null && params[k] !== SE.ALL; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]); }).join("&");
  };

  /* ---------- tata letak ---------- */
  SE.gutter = function () { return SE.isNarrow() ? 10 : 24; };

  SE.filterRow = function (items) {
    /* Pilihan "Semua ..." memakai penanda SE.ALL. Filter dibuka dengan pilihan itu sudah terpilih, supaya kotaknya
       langsung bertuliskan "Semua ..." (bukan kosong); teksnya juga dipasang sebagai placeholder sebagai cadangan. */
    items.forEach(function (it) {
      if (it.view === "richselect" && it.options && it.options[0] && it.options[0].id === SE.ALL) {
        if (!it.value) { it.value = SE.ALL; }
        if (!it.placeholder) { it.placeholder = it.options[0].value; }
      }
    });
    if (SE.isNarrow()) { return { rows: items, margin: 8 }; }

    /* Kotak filter TIDAK dikunci lebar tetap: tiap kotak boleh menyusut sampai lebar minimum dan melebar sampai
       lebar maksimum. Dengan begitu deretan filter selalu muat di layar selebar apa pun (lebar tetap yang kebanyakan
       membuat seluruh halaman terdorong keluar layar). */
    var flex = items.map(function (it) {
      if (it.view === "richselect" || it.view === "combo" || it.view === "datepicker") {
        var c = Object.assign({}, it);
        c.maxWidth = c.maxWidth || c.width || 260;
        delete c.width;
        c.minWidth = c.minWidth || (it.view === "datepicker" ? 135 : 125);
        if (SE.isCompact()) { c.minWidth = it.minWidth ? Math.min(it.minWidth, 140) : 100; }  // tablet: ruang lebih sempit
        return c;
      }
      if (it.view === "tabbar") {
        var t = Object.assign({}, it);
        if (t.options && t.options.length <= 3 && !t.width) { t.width = t.options.length * (t.optionWidth || 150) + 10; }
        else if (!t.width) { t.minWidth = t.minWidth || (SE.isCompact() ? 300 : 360); }
        return t;
      }
      return it;
    });
    /* Bila semua kotak punya batas lebar, sisa ruang dibiarkan kosong di kanan (bukan dilebarkan paksa). */
    if (flex.every(function (it) { return it.maxWidth || it.width; })) { flex.push({}); }
    return { cols: flex, margin: 10, height: 42 };
  };

  function headButton(btn) {
    var b = Object.assign({ height: 40, css: "head-btn" }, btn);
    if (btn.css) { b.css = "head-btn " + btn.css; }
    return { rows: [{}, b, {}], width: (btn.width || 110) + 10 };
  }

  SE.pageHead = function (title, subtitle, buttons) {
    var g = SE.gutter();
    var titleHtml = "<h1>" + SE.esc(title) + "</h1>" + (subtitle ? "<p>" + SE.esc(subtitle) + "</p>" : "");
    if (SE.isNarrow()) {
      var rows = [{ view: "template", borderless: true, css: "page-title", autoheight: true, template: titleHtml }];
      if (buttons && buttons.length) {
        rows.push({ cols: buttons.map(function (b) {
          var c = Object.assign({ height: 42 }, b, { css: "head-btn" + (b.css ? " " + b.css : "") });
          delete c.width;
          return c;
        }), margin: 8, height: 42 });
      }
      return { css: "page-head", paddingX: g, paddingY: 10, margin: 10, rows: rows };
    }
    /* Tinggi kepala halaman mengikuti jumlah baris subjudul (jendela sempit = subjudul bisa 2 baris). */
    var buttonsWidth = (buttons || []).reduce(function (n, b) { return n + (b.width || 110) + 10; }, 0);
    var textWidth = Math.max(window.innerWidth - (SE.isCompact() ? 64 : 236) - 2 * g - buttonsWidth, 220);
    var lines = subtitle ? Math.ceil(subtitle.length * 7.2 / textWidth) : 0;
    return {
      css: "page-head", height: subtitle ? Math.max(92, 66 + lines * 21) : 76, paddingX: g, paddingY: 12,
      cols: [{ view: "template", borderless: true, css: "page-title", template: titleHtml }]
        .concat((buttons || []).map(headButton))
    };
  };

  /* Halaman daftar standar: kepala halaman + satu kartu putih berisi filter, (ringkasan), tabel, dan pagination. */
  SE.listPage = function (cfg) {
    var g = SE.gutter();
    var inside = [];
    if (cfg.filters && cfg.filters.length) { inside.push(SE.filterRow(cfg.filters)); }
    (cfg.before || []).forEach(function (v) { inside.push(v); });
    inside.push(cfg.body || cfg.list.ui);
    return {
      id: cfg.id, on: { onViewShow: cfg.onShow },
      rows: [
        SE.pageHead(cfg.title, cfg.subtitle, cfg.buttons),
        { paddingX: g, paddingY: 12, rows: [{ css: SE.isNarrow() ? "card-flat" : "card", padding: SE.isNarrow() ? 0 : 18,
          margin: SE.isNarrow() ? 10 : 14, rows: inside }] }
      ]
    };
  };

  /* ---------- tabel standar ---------- */
  SE.flatTable = function (cfg) {
    if (SE.isNarrow() && !cfg.keepTable) { return SE.cardList(cfg); }
    var narrowTable = SE.isNarrow() && cfg.keepTable;
    /* Tiap kolom punya lebar minimum yang masih terbaca. Bila jumlahnya melebihi lebar layar, tabel
       otomatis bisa digeser ke kanan-kiri (scrollX) dan tidak ada tulisan yang terpotong. */
    var columns = cfg.columns.map(function (c) {
      var col = Object.assign({}, c);
      if (!col.width && !col.fillspace) { col.fillspace = 1; }
      if (col.fillspace && !col.minWidth) { col.minWidth = narrowTable ? 130 : Math.max(112, Math.round(col.fillspace * 80)); }
      return col;
    });
    var table = {
      view: "datatable", id: cfg.id, scrollX: true, scrollY: cfg.scrollY !== false, rowHeight: cfg.rowHeight || 56, headerRowHeight: 46,
      css: "flat-table" + (cfg.onRowClick ? " row-link" : ""), hover: "tbl-hover", columns: columns,
      onClick: cfg.onClick || {}, on: SE.rowClickEvents(cfg.onRowClick), data: cfg.data || []
    };
    /* cfg.autoRowHeightColumn: baris memanjang mengikuti isi kolom itu (untuk teks panjang yang harus terbaca utuh).
       Tingginya dihitung ulang tiap data dimuat (lihat pagedList). */
    if (cfg.autoRowHeightColumn) { table.fixedRowHeight = false; table.minRowHeight = cfg.rowHeight || 56; }
    return table;
  };

  /* Di HP data ditampilkan sebagai satu kartu per baris (dibuat dari definisi kolom yang sama). */
  SE.cardList = function (cfg) {
    var cols = cfg.columns;
    var preferred = ["product_name", "name", "request_number", "batch_number", "sku"];
    var titleCol = null;
    preferred.some(function (id) { titleCol = cols.filter(function (c) { return c.id === id; })[0]; return !!titleCol; });
    if (!titleCol) { titleCol = cols[0]; }
    var actionCol = cols.filter(function (c) { return c.id === "actions"; })[0];

    function html(col, o) {
      var t = col.template;
      if (typeof t === "function") { return t(o); }
      if (typeof t === "string") { return t.replace(/#(\w+)#/g, function (m, k) { return o[k] == null ? "" : o[k]; }); }
      return SE.esc(o[col.id]);
    }

    function card(o) {
      var badges = "", rows = "";
      cols.forEach(function (c) {
        if (c === titleCol || c === actionCol || !c.header) { return; }
        var v = html(c, o);
        if (v == null || v === "") { return; }
        if (String(v).indexOf("badge") !== -1 && String(v).length < 220) { badges += '<div class="m-badge">' + v + "</div>"; }
        else { rows += '<div class="m-row"><span class="m-k">' + SE.esc(c.header) + '</span><span class="m-v">' + v + "</span></div>"; }
      });
      var acts = actionCol ? html(actionCol, o) : "";
      return '<div class="m-card"><div class="m-head"><div class="m-title">' + html(titleCol, o) + "</div>" + badges + "</div>" +
        (rows ? '<div class="m-rows">' + rows + "</div>" : "") +
        (acts ? '<div class="m-acts">' + acts + "</div>" : "") + "</div>";
    }

    return {
      view: "list", id: cfg.id, css: "m-list" + (cfg.onRowClick ? " row-link" : ""), scroll: cfg.autoheight ? false : "y",
      autoheight: !!cfg.autoheight, borderless: true, type: { height: "auto" }, template: card,
      onClick: cfg.onClick || {}, on: SE.rowClickEvents(cfg.onRowClick), data: cfg.data || []
    };
  };

  SE.rowClickEvents = function (handler) {
    if (!handler) { return {}; }
    return {
      onItemClick: function (id, e) {
        if (e && e.target && e.target.closest && e.target.closest(".act")) { return; }
        handler(this.getItem(id));
      }
    };
  };

  /* ---------- pengajuan yang masih terbuka di sebuah batch ---------- */
  /* Pilihan pengajuan yang BISA diajukan sekarang (yang terhalang pengajuan terbuka tidak ikut). */
  SE.requestable = function (b) {
    return (b.request_options || []).filter(function (o) { return !o.blocked_by; });
  };
  /* Teks singkat "PG-261116-001 (Disetujui)" untuk pengajuan yang masih terbuka. */
  SE.openRequestText = function (b) {
    return (b.open_requests || []).map(function (r) {
      return r.request_number + " (" + (SE.REQUEST_STATUS_LABEL[r.status] || r.status) + ")"; }).join(", ");
  };

  /* ---------- daftar bernomor halaman ---------- */
  SE.pagedList = function (cfg) {
    var state = { page: 1, limit: cfg.limit || 20, total: 0 };
    var tableId = cfg.id + "_tbl", infoId = cfg.id + "_info", prevId = cfg.id + "_prev", nextId = cfg.id + "_next",
      numId = cfg.id + "_num", sizeId = cfg.id + "_size";
    var narrow = SE.isNarrow();

    function pages() { return Math.max(Math.ceil(state.total / state.limit), 1); }

    function refreshBar() {
      var from = state.total ? (state.page - 1) * state.limit + 1 : 0;
      var to = Math.min(state.page * state.limit, state.total);
      $$(infoId).setValue(narrow ? state.total + " data" : "Menampilkan " + from + "&ndash;" + to + " dari " + state.total + " data");
      $$(numId).setHTML("<span>" + state.page + " / " + pages() + "</span>");
      if (state.page <= 1) { $$(prevId).disable(); } else { $$(prevId).enable(); }
      if (state.page >= pages()) { $$(nextId).disable(); } else { $$(nextId).enable(); }
    }

    /* Nomor urut permintaan: bila dua permintaan berjalan bersamaan (misalnya halaman dibuka lalu tab/filter
       langsung diganti), hanya jawaban permintaan TERAKHIR yang ditampilkan. Jawaban lama yang datang
       belakangan diabaikan, supaya isi tabel selalu cocok dengan tab/filter yang terlihat. */
    var lastRequest = 0;

    function reload(reset) {
      if (reset) { state.page = 1; }
      var url = typeof cfg.url === "function" ? cfg.url() : cfg.url;
      var q = SE.query(cfg.params ? cfg.params() : {});
      var paging = "page=" + state.page + "&limit=" + state.limit;
      var mine = ++lastRequest;
      return SE.api("GET", url + "?" + (q ? q + "&" : "") + paging).then(function (res) {
        if (mine !== lastRequest) { return; }
        state.total = res.total || 0;
        var table = $$(tableId);
        table.clearAll();
        table.parse(res.data);
        if (cfg.autoRowHeightColumn && table.adjustRowHeight) {  // baris memanjang mengikuti teks panjang di kolom itu
          table.adjustRowHeight(cfg.autoRowHeightColumn, true);
          table.refresh();
        }
        if (table.showOverlay) {
          if (res.data.length === 0) { table.showOverlay("Tidak ada data yang cocok."); } else { table.hideOverlay(); }
        }
        refreshBar();
        if (cfg.onData) { cfg.onData(res); }
      }).catch(function (err) { SE.toast(err.message, "error"); });
    }

    var pager = {
      css: "pager", height: 48, margin: 8, paddingY: 4,
      cols: [
        { view: "label", id: infoId, label: "", css: "pg-info" },
        { view: "button", id: prevId, value: "&lsaquo;", width: 38, css: "pg-btn", tooltip: "Sebelumnya",
          click: function () { if (state.page > 1) { state.page -= 1; reload(); } } },
        { view: "template", id: numId, width: 78, borderless: true, css: "pg-num", template: "<span>1 / 1</span>" },
        { view: "button", id: nextId, value: "&rsaquo;", width: 38, css: "pg-btn", tooltip: "Berikutnya",
          click: function () { if (state.page < pages()) { state.page += 1; reload(); } } }
      ].concat(narrow ? [] : [
        { view: "richselect", id: sizeId, width: 156, css: "pg-size", value: state.limit, options: [
          { id: 10, value: "10 / halaman" }, { id: 20, value: "20 / halaman" },
          { id: 50, value: "50 / halaman" }, { id: 100, value: "100 / halaman" }],
          on: { onChange: function (v) { state.limit = Number(v); reload(true); } } }
      ])
    };

    return {
      reload: reload,
      ui: { rows: [SE.flatTable({ id: tableId, columns: cfg.columns, rowHeight: cfg.rowHeight,
        autoRowHeightColumn: cfg.autoRowHeightColumn, onClick: cfg.onClick, onRowClick: cfg.onRowClick }), pager] }
    };
  };

  /* ---------- dialog import dari file CSV (periksa dulu, lalu simpan; satu baris salah = tidak ada yang disimpan) ---------- */
  SE.openImport = function (cfg) {
    var winId = "winImport";
    var chosen = null;
    if ($$(winId)) { $$(winId).close(); }

    function render(report) {
      var html = "<div style='padding:6px;line-height:1.5'>" +
        "<b>" + SE.esc(chosen.name) + "</b><br>" +
        "Jumlah baris: " + report.total_rows + " &middot; Benar: " + report.valid_rows +
        " &middot; Perlu diperbaiki: " + report.invalid_rows + "<br>";
      if (report.invalid_rows > 0) {
        html += "<span style='color:#b91c1c'>Belum ada data yang disimpan. Perbaiki baris di bawah ini di file Anda, lalu pilih file lagi.</span><ul>";
        report.errors.forEach(function (e) {
          html += "<li>Baris " + e.row + ": " + SE.esc(e.message) + "</li>";
        });
        html += "</ul>";
        if (report.errors_truncated) { html += "<i>(masih ada kesalahan lain yang tidak ditampilkan)</i>"; }
      } else {
        html += "<span style='color:#166534'>Semua baris sudah benar. Klik \"Simpan Data\" untuk menyimpan.</span>";
      }
      html += "</div>";
      $$("impResult").setHTML(html);
      if (report.invalid_rows === 0 && report.total_rows > 0) { $$("impGo").enable(); } else { $$("impGo").disable(); }
    }

    webix.ui({
      view: "window", id: winId, modal: true, position: "center", move: true,
      width: Math.min(600, window.innerWidth - 20), head: cfg.title,
      body: {
        padding: 14, rows: [
          { view: "template", borderless: true, autoheight: true,
            template: "<div style='line-height:1.6'>1. Unduh contoh file, lalu buka di Excel.<br>" +
              "2. Isi data Anda mulai baris ke-2 (baris pertama adalah judul kolom, jangan diubah).<br>" +
              "3. Simpan lewat <b>File &rsaquo; Save As</b>, pilih jenis <b>CSV UTF-8</b>.<br>" +
              "4. Klik <b>Pilih File</b>, lalu lihat hasil pengecekannya.<br>" +
              "5. Bila semua benar, klik <b>Simpan Data</b>.<br>" +
              "Bila ada satu baris yang salah, <b>belum ada data yang disimpan</b> sampai file diperbaiki.</div>" +
              (cfg.note ? "<br>" + cfg.note : "") },
          { view: "button", value: "Unduh Contoh File",
            click: function () { window.location.href = "/api/v1/imports/templates/" + cfg.kind; } },
          { view: "uploader", value: "Pilih File...", accept: ".csv,text/csv", multiple: false, autosend: false,
            on: {
              onBeforeFileAdd: function (item) {
                chosen = item.file;
                $$("impGo").disable();
                $$("impResult").setHTML("<div style='padding:6px'>Sedang mengecek isi file...</div>");
                SE.upload("/api/v1/imports/" + cfg.kind + "/preview", chosen).then(render).catch(function (err) {
                  chosen = null;
                  $$("impResult").setHTML("<div style='padding:6px;color:#b91c1c'>" + SE.esc(err.message) + "</div>");
                });
                return false;
              }
            } },
          { view: "template", id: "impResult", scroll: "y", height: 220,
            template: "<div style='padding:6px;color:#5b6b7b'>Belum ada file dipilih.</div>" },
          { cols: [
            { view: "button", value: "Tutup", click: function () { $$(winId).close(); } },
            { view: "button", id: "impGo", value: "Simpan Data", css: "webix_primary", disabled: true,
              click: function () {
                $$("impGo").disable();
                SE.upload("/api/v1/imports/" + cfg.kind + "/confirm", chosen).then(function (report) {
                  if (report.applied) {
                    $$(winId).close();
                    SE.toast("Berhasil: " + report.imported + " data ditambahkan dari file.");
                    if (cfg.onDone) { cfg.onDone(); }
                  } else {
                    render(report);
                  }
                }).catch(function (err) { SE.toast(err.message, "error"); });
              } }
          ] }
        ]
      }
    }).show();
  };

  /* Jendela form kecil standar. */
  SE.formWindow = function (cfg) {
    if ($$(cfg.id)) { $$(cfg.id).close(); }
    /* Di layar lebar form setinggi isinya; di layar pendek/ponsel form bisa digulir. */
    var form = { view: "form", id: cfg.id + "Form", padding: 16, elementsConfig: { labelPosition: "top" },
      elements: cfg.elements };
    if (SE.isNarrow() || window.innerHeight < 700) {
      form.scroll = "y";
      form.height = Math.max(window.innerHeight - 110, 300);
    }
    return webix.ui({
      view: "window", id: cfg.id, modal: true, position: "center", move: true,
      width: Math.min(cfg.width || 480, window.innerWidth - 20), head: cfg.title, body: form
    });
  };

  SE.note = function (html) {
    return { view: "template", borderless: true, autoheight: true,
      template: "<span style='color:#5b6b7b;font-size:13px;line-height:1.45'>" + html + "</span>" };
  };

  /* Keterangan singkat di bagian atas form (kotak biru muda). html berisi teks tetap dari kode, bukan isian pengguna. */
  SE.tip = function (html) {
    return { view: "template", borderless: true, autoheight: true, css: "howto",
      template: "<div class='howto-box'>" + html + "</div>" };
  };

  /* Petunjuk kecil tepat di bawah sebuah isian (contoh isi / kapan wajib). */
  SE.hint = function (html, id) {
    var cfg = { view: "template", borderless: true, autoheight: true, css: "field-hint",
      template: "<span class='form-hint'>" + html + "</span>" };
    if (id) { cfg.id = id; }
    return cfg;
  };

  /* ---------- daftar halaman ---------- */
  SE.register = function (mod) { SE.modules.push(mod); };
})();

/* ---------- ganti password sendiri (wajib setelah akun dibuat atau password direset Admin) ---------- */
(function () {
  "use strict";

  SE.openChangePassword = function (forced) {
    var buttons = [];
    if (forced) {
      buttons.push({ view: "button", value: "Keluar", click: function () {
        SE.api("POST", "/api/v1/auth/logout").catch(function () { }).then(function () { window.location.href = "/login"; });
      } });
    } else {
      buttons.push({ view: "button", value: "Batal", click: function () { $$("winChangePw").close(); } });
    }
    buttons.push({ view: "button", value: "Simpan Password", css: "webix_primary", click: function () {
      var v = $$("winChangePwForm").getValues();
      if (v.new_password !== v.confirm) { SE.toast("Ulangi password baru belum sama.", "error"); return; }
      SE.busy(this, SE.api("POST", "/api/v1/auth/change-password",
        { old_password: v.old_password, new_password: v.new_password })).then(function () {
        SE.toast("Password sudah diganti.");
        if (forced) { window.location.reload(); } else { $$("winChangePw").close(); }
      }).catch(function (err) { SE.toast(SE.formErrorText(err), "error"); });
    } });

    var win = SE.formWindow({ id: "winChangePw", title: forced ? "Buat Password Baru" : "Ganti Password", width: 420, elements: [
      SE.note(forced
        ? "Password Anda dibuat atau direset oleh Admin. Demi keamanan, buat <b>password baru milik Anda sendiri</b> " +
          "sebelum memakai aplikasi. Setelah ini, Admin pun tidak tahu password Anda."
        : "Masukkan password lama, lalu password baru. Perangkat lain yang masih masuk dengan akun ini akan keluar otomatis."),
      { view: "text", type: "password", name: "old_password", label: forced ? "Password dari Admin" : "Password lama" },
      { view: "text", type: "password", name: "new_password", label: "Password baru (minimal 8 huruf/angka)" },
      { view: "text", type: "password", name: "confirm", label: "Ulangi password baru" },
      { cols: buttons }
    ] });
    win.show();
  };
})();
