from flask import Blueprint, current_app, session

from ...common.audit import log_action
from ...common.http import json_body, ok
from ...common.permissions import load_current_user, login_required, touch_session
from . import services

bp = Blueprint("auth", __name__)


@bp.post("/login")
def login():
    body = json_body()
    user = services.authenticate(current_app.db, body.get("email"), body.get("password"))
    session.clear()  # sesi baru setiap login
    session["user_id"] = str(user["_id"])
    session["sv"] = user.get("session_version", 0)  # versi sesi; naik bila password diatur ulang
    session.permanent = True  # berakhir sesuai PERMANENT_SESSION_LIFETIME (8 jam)
    touch_session()  # mulai hitung waktu tidak aktif
    return ok(services.profile(user))


@bp.post("/logout")
@login_required
def logout():
    user = load_current_user()
    # Sesi Flask tersimpan di cookie browser. Supaya salinan cookie lama tidak bisa dipakai lagi setelah logout,
    # versi sesi dinaikkan: semua cookie lama akun ini langsung tidak berlaku (juga di perangkat lain).
    current_app.db.master_karyawan.update_one({"_id": user["_id"]}, {"$inc": {"session_version": 1}})
    log_action(current_app.db, user, "logout", "master_karyawan", user["_id"])
    session.clear()
    return ok({"message": "Berhasil keluar."})


@bp.get("/me")
@login_required
def me():
    return ok(services.profile(load_current_user()))


@bp.post("/change-password")
@login_required
def change_password():
    user = services.change_password(current_app.db, load_current_user(), json_body())
    session["sv"] = user.get("session_version", 0)  # sesi ini tetap berlaku, sesi lama lain berakhir
    return ok(services.profile(user))
