/* Manajemen Pengguna (khusus Admin, SD 4.1): tambah akun, ubah nama/peran, aktifkan/nonaktifkan, atur ulang password.
   Akun tidak pernah dihapus. Admin aktif terakhir tidak dapat dinonaktifkan atau diturunkan perannya. */
(function () {
  "use strict";

  var esc = SE.esc, api = SE.api, toast = SE.toast;
  var userList;

  var ROLE_OPTIONS = [
    { id: "staff", value: "Staff" }, { id: "supervisor", value: "Supervisor" }, { id: "admin", value: "Admin" }
  ];

  function toggleUser(user, done) {
    var action = user.is_active ? "deactivate" : "activate";
    var question = user.is_active
      ? "Nonaktifkan akun " + user.email + "? Orang ini tidak bisa masuk ke aplikasi lagi."
      : "Aktifkan kembali akun " + user.email + "?";
    webix.confirm({ title: "Konfirmasi", text: esc(question), ok: "Ya", cancel: "Batal" }).then(function () {
      return api("POST", "/api/v1/users/" + user.id + "/" + action);
    }).then(function () { toast("Status akun diperbarui."); done(); })
      .catch(function (err) { if (err && err.message) { toast(err.message, "error"); } });
  }

  function resetPassword(user) {
    var win = SE.formWindow({ id: "winReset", title: "Ganti Password", width: 420, elements: [
      SE.note("Password baru untuk <b>" + esc(user.email) + "</b>. Beri tahu password ini langsung ke orangnya (jangan lewat grup chat). " +
        "Saat masuk nanti, ia <b>wajib membuat password baru sendiri</b>, jadi Admin tidak tahu password yang dipakai sehari-hari."),
      { view: "text", type: "password", name: "new_password", label: "Password baru (minimal 8 huruf/angka)" },
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winReset").close(); } },
        { view: "button", value: "Simpan", css: "webix_primary", click: function () {
          SE.busy(this, api("POST", "/api/v1/users/" + user.id + "/reset-password", $$("winResetForm").getValues()))
            .then(function () { $$("winReset").close(); toast("Password sudah diganti."); })
            .catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ] });
    win.show();
  }

  function openUserDetail(id) {
    api("GET", "/api/v1/users/" + id).then(function (res) {
      var user = res.data;
      var reopen = function () { openUserDetail(user.id); };
      var isSelf = user.id === SE.me.id;
      var form = SE.detailForm({
        id: "udForm", canEdit: true,
        values: { name: user.name, email: user.email, role: user.role,
          status: (user.is_active ? "Aktif" : "Nonaktif") + (user.locked_minutes
            ? " · dikunci " + user.locked_minutes + " menit lagi (salah password 5 kali). Ganti password untuk membuka." : ""),
          last_login: user.last_login_at ? SE.fmtDateTime(user.last_login_at) : "Belum pernah masuk" },
        rows: [
          [{ view: "text", name: "name", label: "Nama" }, { view: "text", name: "email", label: "Email", locked: true }],
          [{ view: "richselect", name: "role", label: "Peran", options: ROLE_OPTIONS, locked: isSelf },
            { view: "text", name: "status", label: "Status akun", locked: true }],
          { view: "text", name: "last_login", label: "Terakhir masuk", locked: true }
        ],
        onSave: function (v) { return api("PUT", "/api/v1/users/" + user.id, { name: v.name, role: v.role }); },
        afterSave: reopen
      });
      var buttons = [{ view: "button", value: "Ganti password", width: 150, click: function () { resetPassword(user); } }];
      if (!isSelf) {
        buttons.push({ view: "button", value: user.is_active ? "Nonaktifkan akun" : "Aktifkan akun", width: 160,
          css: user.is_active ? "danger-btn" : "", click: function () { toggleUser(user, reopen); } });
      }
      SE.showDetail({ parentId: "users", parentTitle: "Pengguna", title: user.name, buttons: buttons, body: form.ui, init: form.start });
    }).catch(function (err) { toast(err.message, "error"); });
  }

  function openUserForm() {
    var win = SE.formWindow({ id: "winUser", title: "Tambah Pengguna", width: 460, elements: [
      SE.tip("Staff mengelola stok toko, Supervisor menyetujui pengajuan, Admin mengelola akun. Berikan password awal " +
        "langsung ke orangnya; saat pertama masuk ia diminta membuat password sendiri."),
      { view: "text", name: "name", label: "Nama" },
      { view: "text", name: "email", label: "Email" },
      { view: "richselect", name: "role", label: "Peran", value: "staff", options: ROLE_OPTIONS },
      { view: "text", type: "password", name: "password", label: "Password awal (minimal 8 huruf/angka)" },
      { cols: [
        { view: "button", value: "Batal", click: function () { $$("winUser").close(); } },
        { view: "button", value: "Simpan", css: "webix_primary", click: function () {
          SE.busy(this, api("POST", "/api/v1/users", $$("winUserForm").getValues())).then(function () {
            $$("winUser").close();
            toast("Pengguna disimpan.");
            userList.reload();
          }).catch(function (err) { toast(SE.formErrorText(err), "error"); });
        } }
      ] }
    ] });
    win.show();
  }

  SE.register({
    id: "users", title: "Pengguna", icon: "wxi-user", order: 90, roles: ["admin"],
    build: function () {
      userList = SE.pagedList({
        id: "usr", url: "/api/v1/users", rowHeight: 56,
        params: function () { return { role: $$("uRole").getValue(), is_active: $$("uActive").getValue() }; },
        columns: [
          { id: "name", header: "Nama", fillspace: 2, template: function (o) { return esc(o.name); } },
          { id: "email", header: "Email", fillspace: 2.6, template: function (o) { return esc(o.email); } },
          { id: "role", header: "Peran", fillspace: 1.2, template: function (o) { return esc(SE.ROLE_LABEL[o.role] || o.role); } },
          { id: "last_login_at", header: "Terakhir masuk", fillspace: 1.5, template: function (o) { return SE.dateTwoLine(o.last_login_at); } },
          { id: "is_active", header: "Status", width: 130, template: function (o) {
            return SE.activeBadge(o.is_active) + (o.locked_minutes ? " <span class='badge fit-partial'>terkunci</span>" : ""); } }
        ],
        onRowClick: function (item) { openUserDetail(item.id); }
      });
      return SE.listPage({
        id: "users", title: "Manajemen Pengguna", subtitle: "Daftar akun dan tugasnya. Akun tidak bisa dihapus; bila orangnya sudah tidak bekerja, nonaktifkan saja.",
        onShow: function () { userList.reload(true); }, list: userList,
        buttons: [{ view: "button", value: "+ Tambah Pengguna", css: "webix_primary", width: 170, click: openUserForm }],
        filters: [
          { view: "richselect", id: "uRole", value: "", options: [{ id: "", value: "Semua peran" }].concat(ROLE_OPTIONS),
            on: { onChange: function () { userList.reload(true); } } },
          { view: "richselect", id: "uActive", value: "", options: [{ id: "", value: "Semua status" }, { id: "true", value: "Aktif" },
            { id: "false", value: "Nonaktif" }], on: { onChange: function () { userList.reload(true); } } }
        ]
      });
    }
  });
})();
