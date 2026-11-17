"""Pemeriksaan login dan peran. Semua dicek di backend, bukan di tampilan (SD 11.2).

- Sesi berakhir bila tidak ada aktivitas selama IDLE_TIMEOUT_MINUTES. Permintaan latar belakang (pengecekan
  lonceng otomatis, header X-Background: 1) tidak dihitung sebagai aktivitas.
- Pengguna yang wajib mengganti password (akun baru atau password direset Admin) hanya boleh memanggil
  endpoint untuk mengganti password, melihat profil, dan logout.
"""
import time
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app, g, redirect, request, session, url_for

from .constants import IDLE_TIMEOUT_MINUTES
from .errors import Forbidden, Unauthorized

IDLE_MESSAGE = (f"Sesi berakhir karena tidak ada aktivitas selama {IDLE_TIMEOUT_MINUTES} menit. "
                "Silakan masuk lagi.")
# Endpoint yang tetap boleh dipakai saat pengguna wajib mengganti password
PASSWORD_CHANGE_ENDPOINTS = {"auth.me", "auth.logout", "auth.change_password"}


def touch_session():
    """Catat waktu aktivitas terakhir (dipanggil saat login dan pada setiap permintaan pengguna)."""
    session["seen"] = int(time.time())


def load_current_user():
    """Ambil pengguna dari sesi. Pengguna dimuat ulang di SETIAP request, jadi akun yang dinonaktifkan
    atau perannya diubah langsung berlaku tanpa menunggu logout."""
    if hasattr(g, "current_user"):
        return g.current_user
    user = None
    raw_id = session.get("user_id")
    if raw_id:
        try:
            user = current_app.db.master_karyawan.find_one({"_id": ObjectId(raw_id), "is_active": True})
        except (InvalidId, TypeError):
            user = None
        # Password diatur ulang -> versi sesi naik -> sesi lama (yang dibuat sebelum reset) tidak berlaku lagi.
        if user is not None and session.get("sv", 0) != user.get("session_version", 0):
            user = None
        if user is not None:
            seen = session.get("seen")
            if seen is None or time.time() - seen > IDLE_TIMEOUT_MINUTES * 60:
                user = None
                g.idle_expired = True
            elif request.headers.get("X-Background") != "1":
                touch_session()
        if user is None:
            session.clear()  # nonaktif, password diganti, logout di tempat lain, atau terlalu lama tidak aktif
    g.current_user = user
    return user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if user is None:
            raise Unauthorized(IDLE_MESSAGE if g.get("idle_expired") else "Silakan masuk (login) dulu.")
        if user.get("must_change_password") and request.endpoint not in PASSWORD_CHANGE_ENDPOINTS:
            raise Forbidden("Ganti password Anda dulu sebelum memakai aplikasi.")
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if load_current_user()["role"] not in roles:
                raise Forbidden("Anda tidak memiliki akses untuk tindakan ini.")
            return view(*args, **kwargs)
        return wrapper
    return decorator


def page_login_required(view):
    """Untuk halaman HTML: kalau belum login, arahkan ke halaman login."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if load_current_user() is None:
            return redirect(url_for("pages.login_page", reason="idle") if g.get("idle_expired")
                            else url_for("pages.login_page"))
        return view(*args, **kwargs)
    return wrapper
