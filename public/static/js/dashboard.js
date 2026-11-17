/* Dashboard (SD 5.1): ringkasan produk, stok tersedia, batch per status, dan pengajuan.
   Semua angka dihitung dari database saat halaman dibuka. Bagian bertanda › bisa diklik. */
(function () {
  "use strict";

  var esc = SE.esc;

  var FILL = { normal: "#3fb27f", monitoring: "#5b8def", near_expired: "#f2b134", critical: "#ef6a5b", expired: "#b8322f" };

  function greeting() {
    var hour = Number(new Date().toLocaleString("en-GB", { timeZone: "Asia/Jakarta", hour: "2-digit", hour12: false })) % 24;
    if (hour < 11) { return "Selamat pagi"; }
    if (hour < 15) { return "Selamat siang"; }
    if (hour < 18) { return "Selamat sore"; }
    return "Selamat malam";
  }

  function todayText() {
    return new Date().toLocaleDateString("id-ID", {
      timeZone: "Asia/Jakarta", weekday: "long", day: "numeric", month: "long", year: "numeric"
    });
  }

  function linkAttrs(go, view) {
    return go ? ' class="card-link" role="button" tabindex="0" data-go="' + esc(go) + '" data-view="' + esc(view || "") + '"' : "";
  }

  function stat(label, value, hint, go, view, warn, cta) {
    return "<div" + linkAttrs(go, view) + '><div class="stat ' + (go ? "stat-link" : "") + '">' +
      '<div class="stat-label">' + esc(label) + "</div>" +
      '<div class="stat-value">' + esc(value) + "</div>" +
      '<div class="stat-hint' + (warn ? " stat-warn" : "") + '">' + esc(hint) + "</div>" +
      (go ? '<div class="stat-cta">' + esc(cta || "Buka") + " &rsaquo;</div>" : "") + "</div></div>";
  }

  function header() {
    var me = SE.me;
    return '<div class="dash-head"><div>' +
      '<h1 class="dash-hello">' + greeting() + ", <b>" + esc(me.name) + "</b></h1>" +
      '<p class="dash-sub">' + esc(SE.ROLE_LABEL[me.role] || me.role) + " &middot; ringkasan stok toko hari ini</p></div>" +
      '<div class="date-pill">' + esc(todayText()) + "</div></div>";
  }

  function statStrip(s) {
    var html = '<div class="stat-strip">' +
      stat("Produk aktif", s.total_active_products, "jenis produk yang dijual", "products", "", false, "Lihat produk") +
      stat("Stok tersedia", s.total_available_stock, "barang yang boleh dijual", "", "") +
      stat("Menunggu persetujuan", s.pending_requests,
        s.pending_requests ? "pengajuan menunggu Supervisor" : "tidak ada yang menunggu",
        "requests", "pending", s.pending_requests > 0, SE.isSupervisor() ? "Tinjau sekarang" : "Buka pengajuan");
    if (s.approved_open_requests !== undefined) {
      html += stat("Disetujui, belum selesai", s.approved_open_requests,
        s.approved_open_requests ? "kerjakan, lalu tandai Selesai" : "semua sudah selesai",
        "requests", "approved", s.approved_open_requests > 0, "Selesaikan");
    } else {
      html += stat("Barang kedaluwarsa", s.expired_units, s.expired_units ? "masih ada di stok, belum ditangani" : "tidak ada",
        "monitoring", "expired", s.expired_units > 0, "Lihat");
    }
    return html + "</div>";
  }

  /* Baris kedua: hal yang perlu diawasi (stok menipis, barang rusak, penyesuaian stok, koreksi tanggal). */
  function watchStrip(s) {
    var canReport = SE.isSupervisor() || SE.isAdmin();
    var html = '<div class="stat-strip stat-strip-2">' +
      stat("Stok menipis", s.low_stock_products, s.low_stock_products ? "produk perlu dipesan ulang" : "semua stok cukup",
        canReport ? "reports" : "", "low-stock", s.low_stock_products > 0, "Lihat daftar") +
      stat("Barang rusak", s.damaged_units, s.damaged_units ? "dipisahkan, menunggu pengembalian/pemusnahan" : "tidak ada",
        "recommendations", "", s.damaged_units > 0, "Lihat saran");
    if (SE.isStaff()) {
      html += stat("Perlu cek fisik", s.check_due, s.check_due ? "kiriman sudah waktunya dicek" : "semua sesuai jadwal",
        "monitoring", "check_due", s.check_due > 0, "Lihat daftar");
    }
    if (s.recent_adjustments !== undefined) {
      html += stat("Stok disamakan", s.recent_adjustments, s.recent_adjustments ? "dalam " + s.adjustment_days + " hari terakhir, belum dicek ulang" : "semua sudah dicek ulang",
        "reports", "adjustments", false, "Lihat riwayat");
    } else {
      html += stat("Barang kedaluwarsa", s.expired_units, s.expired_units ? "masih ada di stok, belum ditangani" : "tidak ada",
        "monitoring", "expired", s.expired_units > 0, "Lihat");
    }
    if (s.pending_corrections !== undefined) {
      html += stat("Koreksi tanggal", s.pending_corrections,
        s.pending_corrections ? "usulan dari cek fisik menunggu Anda" : "tidak ada usulan",
        "inspections", "pending", s.pending_corrections > 0, "Tinjau");
    }
    return html + "</div>";
  }

  function distribution(s) {
    var total = SE.STATUS_ORDER.reduce(function (n, k) { return n + (s.by_status[k] || 0); }, 0);
    var bar = total === 0
      ? '<div class="dist-empty">Belum ada stok barang.</div>'
      : '<div class="dist-bar">' + SE.STATUS_ORDER.filter(function (k) { return s.by_status[k] > 0; }).map(function (k) {
        return '<span style="width:' + (s.by_status[k] * 100 / total) + "%;background:" + FILL[k] + '" title="' +
          esc(SE.STATUS_LABEL[k]) + '"></span>';
      }).join("") + "</div>";

    var rows = SE.STATUS_ORDER.map(function (k) {
      var n = s.by_status[k] || 0;
      var pct = total ? Math.round(n * 100 / total) : 0;
      var go = k === "normal" ? "batches" : "monitoring";
      return "<div" + linkAttrs(go, k === "normal" ? "normal" : k) + '><div class="dist-row">' +
        '<span class="dot" style="background:' + FILL[k] + '"></span>' +
        '<span class="dist-name">' + esc(SE.STATUS_LABEL[k]) + "</span>" +
        '<span class="dist-n">' + esc(n) + '</span><span class="dist-pct">' + pct + '%</span><span class="dist-go">&rsaquo;</span></div></div>';
    }).join("");

    return '<section class="panel"><h2 class="panel-title">Kondisi tanggal kedaluwarsa</h2>' +
      '<p class="panel-sub">Dari ' + esc(total) + " kiriman barang yang masih ada stoknya</p>" + bar + '<div class="dist-list">' + rows + "</div></section>";
  }

  function urgent(s) {
    var n = (s.by_status.expired || 0) + (s.by_status.critical || 0);
    var body = n === 0
      ? '<div class="hl-big">0</div><p class="hl-text">Tidak ada barang yang sudah kedaluwarsa atau tinggal beberapa hari.</p>'
      : '<div class="hl-big">' + esc(n) + '</div><p class="hl-text">kiriman kedaluwarsa (' + esc(s.by_status.expired || 0) +
        ") atau Kritis (" + esc(s.by_status.critical || 0) + "). Barang kedaluwarsa tidak boleh dijual: ambil dari rak, lalu ajukan pengembalian atau pemusnahan.</p>";
    return '<section class="panel panel-hl"><h2 class="hl-title">Perlu tindakan</h2>' + body +
      '<div' + linkAttrs("recommendations", "") + '><span class="hl-btn">Lihat saran &rsaquo;</span></div></section>';
  }

  function openFromCard(target) {
    var el = target && target.closest ? target.closest(".card-link") : null;
    if (!el) { return; }
    var page = el.getAttribute("data-go"), view = el.getAttribute("data-view");
    if (page === "batches") { SE.go("batches"); if ($$("bStatus")) { $$("bStatus").setValue(view || ""); } return; }
    SE.go(page, view);
  }

  function load() {
    SE.api("GET", "/api/v1/dashboard/summary").then(function (res) {
      var s = res.data;
      $$("dashBody").setHTML('<div class="dash">' + header() + statStrip(s) + watchStrip(s) +
        '<div class="dash-grid">' + distribution(s) + urgent(s) + "</div>" +
        '<p class="dash-note">Status selalu dihitung dari tanggal hari ini. ' +
        "Barang yang tanggal kedaluwarsanya hari ini sudah dianggap kedaluwarsa. Jumlah stok berasal dari catatan di " +
        "aplikasi ini, bukan dari mesin kasir.</p></div>");
    }).catch(function (err) { SE.toast(err.message, "error"); });
  }

  SE.register({
    id: "dashboard", title: "Dashboard", icon: "wxi-columns", order: 0,
    build: function () {
      return {
        id: "dashboard", on: { onViewShow: load },
        rows: [{
          view: "template", id: "dashBody", css: "dash-view", scroll: "y", borderless: true, template: "",
          onClick: { "card-link": function (e) { openFromCard(e.target || e.srcElement); } },
          on: {
            onAfterRender: function () {
              var node = this.getNode();
              if (node && !node._kbd) {
                node._kbd = true;
                node.addEventListener("keydown", function (e) { if (e.key === "Enter") { openFromCard(e.target); } });
              }
            }
          }
        }]
      };
    }
  });
})();
