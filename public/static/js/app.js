/* Kerangka aplikasi: toolbar, menu samping sesuai peran, dan pemuatan halaman-halaman modul. */
(function () {
  "use strict";

  function visibleModules() {
    return SE.modules
      .filter(function (m) { return !m.roles || m.roles.indexOf(SE.me.role) !== -1; })
      .sort(function (a, b) { return a.order - b.order; });
  }

  function logout(notice) {
    SE.api("POST", "/api/v1/auth/logout").catch(function () { }).then(function () {
      if (notice) { try { sessionStorage.setItem("loginNotice", notice); } catch (e) { } }
      window.location.href = "/login";
    });
  }

  /* ---------- keluar otomatis bila tidak ada aktivitas ----------
     Gerakan mouse, ketikan, klik, sentuhan, dan gulir dihitung sebagai aktivitas. Selama pengguna aktif, sesi di
     server diperpanjang tiap beberapa menit. Bila tidak ada aktivitas selama batas waktu, aplikasi keluar sendiri.
     Server juga memeriksa batas ini, jadi tetap aman walaupun halaman dibiarkan terbuka. */
  function startIdleWatch() {
    var limit = (SE.me.idle_timeout_minutes || 30) * 60 * 1000;
    var lastActivity = Date.now(), lastPing = Date.now(), warned = false;
    function activity() { lastActivity = Date.now(); warned = false; }
    ["mousemove", "mousedown", "keydown", "touchstart", "wheel", "scroll"].forEach(function (name) {
      window.addEventListener(name, activity, { passive: true, capture: true });
    });
    setInterval(function () {
      var idle = Date.now() - lastActivity;
      if (idle >= limit) {
        logout("Sesi berakhir karena tidak ada aktivitas selama " + (SE.me.idle_timeout_minutes || 30) + " menit. Silakan masuk lagi.");
        return;
      }
      if (idle >= limit - 60000 && !warned) {
        warned = true;
        webix.message({ type: "error", text: "Tidak ada aktivitas. Anda akan keluar otomatis dalam 1 menit.", expire: 15000 });
      }
      /* pengguna aktif tetapi tidak menyimpan apa pun: beri tahu server bahwa sesi masih dipakai */
      if (lastActivity > lastPing && Date.now() - lastPing >= 5 * 60000) {
        lastPing = Date.now();
        SE.api("GET", "/api/v1/auth/me").catch(function () { });
      }
    }, 15000);
  }

  /* ---------- responsif saat ukuran jendela berubah ----------
     Tata letak (HP / tablet / laptop) ditentukan saat halaman dibangun. Bila jendela diperbesar atau diperkecil
     sampai pindah kelompok, halaman dimuat ulang sendiri supaya tampilannya menyesuaikan. Selama ada form
     yang terbuka, pemuatan ulang ditunda supaya isian tidak hilang. Perubahan kecil di dalam satu kelompok
     tidak memuat ulang apa pun (tabel cukup bisa digeser kanan-kiri). */
  function watchResize() {
    var mode = SE.layoutMode(), timer = null;
    function formOpen() {
      return Array.prototype.some.call(document.querySelectorAll(".webix_modal_cover, .webix_modal"), function (n) {
        return n.offsetParent !== null || n.style.display !== "none"; });
    }
    function check() {
      timer = null;
      if (SE.layoutMode() === mode) { return; }
      if (formOpen()) { timer = setTimeout(check, 3000); return; }
      window.location.reload();
    }
    window.addEventListener("resize", function () {
      if (timer) { clearTimeout(timer); }
      timer = setTimeout(check, 500);
    });
  }

  /* Pindah ke halaman lain (dipakai kartu dashboard). `view` memilih tab/filter di halaman tujuan. */
  SE.go = function (pageId, view) {
    if (!pageId || !$$("sidebar").getItem(pageId)) { return; }
    $$("sidebar").select(pageId);
    if (pageId === "monitoring" && $$("monView")) { $$("monView").setValue(view || ""); }
    if (pageId === "requests" && $$("rqStatus")) { $$("rqStatus").setValue(view || ""); }
    if (pageId === "reports" && view && SE.openReport) { SE.openReport(view); }
    if (pageId === "inspections" && $$("iDiff")) { $$("iDiff").setValue(view || ""); }
  };

  /* Menu dikelompokkan dengan label kecil. Modul tanpa kelompok masuk "Lainnya". */
  var GROUP_OF = {
    dashboard: "Menu utama",
    products: "Stok", batches: "Stok", movements: "Stok",
    monitoring: "Kedaluwarsa", inspections: "Kedaluwarsa", recommendations: "Kedaluwarsa", requests: "Kedaluwarsa",
    reports: "Laporan", activity: "Laporan",
    users: "Pengaturan"
  };

  /* Urutan menu: mengikuti kelompok, bukan angka order, supaya label kelompok tidak muncul dua kali. */
  var MENU_ORDER = ["dashboard", "products", "batches", "movements", "monitoring", "inspections",
    "recommendations", "requests", "reports", "activity", "users"];
  function menuRank(m) { var i = MENU_ORDER.indexOf(m.id); return i === -1 ? 999 : i; }

  function sidebarData(modules) {
    var data = [], last = null;
    modules.slice().sort(function (x, y) { return menuRank(x) - menuRank(y); }).forEach(function (m) {
      var group = GROUP_OF[m.id] || "Lainnya";
      if (group !== last) {
        data.push({ id: "sec_" + data.length, value: group, $css: "side-section" });
        last = group;
      }
      data.push({ id: m.id, value: m.title, icon: m.icon });
    });
    return data;
  }

  function initial(name) { return String(name || "?").trim().charAt(0).toUpperCase(); }

  function buildApp() {
    var modules = visibleModules();
    var narrow = SE.isNarrow();

    var sidebar = {
      /* tablet / setengah layar: menu diciutkan jadi ikon supaya isi halaman lebih lega (hamburger membukanya) */
      view: "sidebar", id: "sidebar", width: 236, collapsedWidth: 64, collapsed: !narrow && SE.isCompact(), scroll: "y",
      data: sidebarData(modules),
      on: {
        onBeforeSelect: function (id) { return String(id).indexOf("sec_") !== 0; },
        onAfterSelect: function (id) {
          $$("pages").setValue(id);
          if (narrow && $$("navPopup")) { $$("navPopup").hide(); }
        },
        /* Saat halaman detail terbuka, menu induk masih terpilih. Klik ulang menu itu = kembali ke daftar. */
        onItemClick: function (id) {
          if (String(id).indexOf("sec_") === 0) { return; }
          if ($$("pages").getValue() !== id) { $$("pages").setValue(id); }
          if (narrow && $$("navPopup")) { $$("navPopup").hide(); }
        }
      }
    };

    /* Di HP, menu tidak makan tempat: tampil sebagai laci di atas konten saat hamburger ditekan. */
    if (narrow) {
      webix.ui({
        view: "popup", id: "navPopup", width: 250, height: Math.max(window.innerHeight - 70, 240),
        css: "nav-popup", padding: 0, body: sidebar
      });
    }

    webix.ui({
      id: "root",
      rows: [
        { view: "toolbar", css: "app-toolbar", height: 58, paddingY: 9, paddingX: 10, cols: [
          { view: "button", id: "menuBtn", value: "&#9776;", css: "webix_transparent menu-btn", width: 48,
            click: function () {
              if (narrow) { $$("navPopup").show($$("menuBtn").getNode(), { x: -8, y: 4 }); }
              else { $$("sidebar").toggle(); }
            } },
          { view: "label", label: "Smart<b>Expiry</b>", css: "app-title", minWidth: narrow ? 100 : 130, width: narrow ? 110 : 150 },
          {},
          /* tombol Panduan bersifat tambahan: bila filenya belum termuat, aplikasi tetap jalan tanpa tombol itu */
          SE.guideButton ? SE.guideButton() : { width: 1 },
          SE.bellButton(),
          { view: "template", css: "who who-link", borderless: true, width: SE.isCompact() ? 50 : 280,
            onClick: { "who-click": function () { SE.openChangePassword(false); } },
            template: '<span class="who-click" title="Klik untuk mengganti password (' + SE.esc(SE.me.name) + ')"><span class="avatar">' + SE.esc(initial(SE.me.name)) + "</span>" +
              (SE.isCompact() ? "" : '<span class="who-text">' + SE.esc(SE.me.name) + "<small>" + SE.esc(SE.ROLE_LABEL[SE.me.role]) +
                " · ganti password</small></span>") + "</span>" },
          { view: "button", value: "Keluar", css: "ghost-btn", width: narrow ? 70 : 86, click: function () { logout(); } }
        ] },
        { cols: (narrow ? [] : [sidebar]).concat([
          { view: "multiview", id: "pages", animate: false, cells: modules.map(function (m) { return m.build(); }).concat([SE.detailCell()]) }
        ]) }
      ]
    });
    SE.startNotifications();
    startIdleWatch();
    watchResize();
    $$("sidebar").select(modules[0].id);
    /* Halaman pertama sudah tampil sejak awal, jadi Webix tidak memicu onViewShow. Panggil sendiri. */
    var first = $$(modules[0].id);
    if (first) { first.callEvent("onViewShow", []); }
  }

  webix.ready(function () {
    SE.api("GET", "/api/v1/auth/me").then(function (res) {
      SE.me = res.data;
    }).then(function () {
      /* akun baru / password direset Admin: wajib membuat password sendiri dulu */
      if (SE.me.must_change_password) { SE.openChangePassword(true); return; }
      buildApp();
    }).catch(function (err) {
      /* Jangan lempar ke /login untuk error biasa: /login akan mengembalikan ke /app dan halaman berputar terus.
         Kasus belum login (401) sudah dialihkan oleh SE.api. */
      var box = document.createElement("div");
      box.style.cssText = "max-width:560px;margin:60px auto;padding:20px;font-family:sans-serif;line-height:1.5;" +
        "border:1px solid #f3b9b9;background:#fdeaea;border-radius:12px;color:#7f1d1d";
      box.innerHTML = "<b>Aplikasi gagal dimuat.</b><br>" + SE.esc((err && err.message) || err) +
        "<br><br>Coba muat ulang dengan Ctrl+F5. Bila tetap gagal, kirim pesan ini ke pembuat aplikasi." +
        '<br><br><a href="/app">Muat ulang</a> &middot; <a href="/login">Ke halaman login</a>';
      document.body.innerHTML = "";
      document.body.appendChild(box);
      if (window.console) { console.error(err); }
    });
  });
})();
