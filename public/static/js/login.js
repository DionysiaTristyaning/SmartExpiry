(function () {
  "use strict";

  var form = document.getElementById("loginForm");
  var errorBox = document.getElementById("loginError");
  var button = document.getElementById("loginBtn");
  var pw = document.getElementById("password");
  var csrf = document.querySelector('meta[name="csrf-token"]').getAttribute("content");

  document.getElementById("togglePw").addEventListener("click", function () {
    var hidden = pw.type === "password";
    pw.type = hidden ? "text" : "password";
    this.textContent = hidden ? "Sembunyi" : "Lihat";
  });

  /* pesan dari halaman aplikasi, misalnya "Sesi berakhir karena tidak ada aktivitas" */
  (function showNotice() {
    var text = "";
    try { text = sessionStorage.getItem("loginNotice") || ""; sessionStorage.removeItem("loginNotice"); } catch (e) { }
    if (!text && /[?&]reason=idle/.test(window.location.search)) {
      text = "Sesi berakhir karena tidak ada aktivitas. Silakan masuk lagi.";
    }
    if (text && text !== "Silakan masuk (login) dulu.") {
      errorBox.textContent = text;
      errorBox.hidden = false;
    }
  })();

  function showError(text) {
    errorBox.textContent = text;
    errorBox.hidden = false;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    errorBox.hidden = true;

    var email = document.getElementById("email").value.trim();
    var password = pw.value;
    if (!email || !password) {
      showError("Email dan password wajib diisi.");
      return;
    }

    button.disabled = true;
    button.textContent = "Sedang masuk...";
    fetch("/api/v1/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, "Accept": "application/json" },
      body: JSON.stringify({ email: email, password: password })
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          if (!res.ok) {
            throw new Error((body.error && body.error.message) || "Gagal masuk. Coba lagi.");
          }
          window.location.href = "/app";
        });
      })
      .catch(function (err) {
        showError(err.message);
        button.disabled = false;
        button.textContent = "Masuk";
      });
  });
})();
