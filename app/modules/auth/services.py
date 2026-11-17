"""Logika login (SD 11.1). Route hanya meneruskan data ke sini.

Perlindungan tebak password: setelah MAX_FAILED_LOGINS kali salah password BERTURUT-TURUT, akun dikunci
sementara selama LOGIN_LOCK_MINUTES. Login yang berhasil mengembalikan hitungan ke 0. Admin juga dapat
membuka kunci dengan mengatur ulang password. Semua kejadian tercatat di Riwayat Aktivitas.
"""
import math
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument
from werkzeug.security import check_password_hash, generate_password_hash

from ...common.audit import log_action
from ...common.constants import IDLE_TIMEOUT_MINUTES, LOGIN_LOCK_MINUTES, MAX_FAILED_LOGINS, ROLE_LABELS
from ...common.errors import Unauthorized, ValidationFailed

GENERIC_LOGIN_ERROR = "Email atau password salah."

# Dipakai agar waktu respon sama, baik email terdaftar maupun tidak.
_DUMMY_HASH = generate_password_hash("password-palsu-untuk-penyamaran")


def authenticate(db, email, password):
    """Kembalikan dokumen user jika login benar. Jika salah, pesan selalu sama (tidak membocorkan email)."""
    if not isinstance(email, str) or not isinstance(password, str):
        raise ValidationFailed("Email dan password wajib diisi.")
    email = email.strip().lower()
    if not email or not password:
        raise ValidationFailed("Email dan password wajib diisi.")

    user = db.master_karyawan.find_one({"email": email})
    stored_hash = user["password_hash"] if user else _DUMMY_HASH
    password_ok = check_password_hash(stored_hash, password)
    now = datetime.now(timezone.utc)

    minutes = locked_minutes_left(user, now)
    if minutes:
        log_action(db, user, "login_failed", "master_karyawan", user["_id"], details={"email": email[:120], "reason": "locked"})
        raise Unauthorized(f"Akun ini dikunci sementara karena password salah {MAX_FAILED_LOGINS} kali. "
                           f"Coba lagi dalam {minutes} menit, atau minta Admin mengganti password.")

    if not user or not password_ok or not user.get("is_active", False):
        reason = "unknown_email" if not user else ("inactive" if not user.get("is_active", False) else "bad_password")
        log_action(db, user, "login_failed", "master_karyawan", user["_id"] if user else None,
                   details={"email": email[:120], "reason": reason})
        if reason == "bad_password" and _count_failure(db, user, now):
            raise Unauthorized(f"Password salah {MAX_FAILED_LOGINS} kali. Demi keamanan, akun ini dikunci "
                               f"{LOGIN_LOCK_MINUTES} menit.")
        raise Unauthorized(GENERIC_LOGIN_ERROR)

    db.master_karyawan.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now, "failed_logins": 0, "locked_until": None}})
    log_action(db, user, "login_success", "master_karyawan", user["_id"])
    return user


def _aware(value):
    if value is not None and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def locked_minutes_left(user, now=None):
    """Sisa menit kunci login (dibulatkan ke atas); 0 bila tidak terkunci."""
    until = _aware((user or {}).get("locked_until"))
    now = now or datetime.now(timezone.utc)
    if not until or until <= now:
        return 0
    return max(1, math.ceil((until - now).total_seconds() / 60))


def _count_failure(db, user, now):
    """Tambah hitungan salah password. Mengembalikan True bila akun baru saja dikunci."""
    updated = db.master_karyawan.find_one_and_update({"_id": user["_id"]}, {"$inc": {"failed_logins": 1}},
                                           return_document=ReturnDocument.AFTER)
    if updated.get("failed_logins", 0) < MAX_FAILED_LOGINS:
        return False
    until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
    db.master_karyawan.update_one({"_id": user["_id"]}, {"$set": {"failed_logins": 0, "locked_until": until}})
    log_action(db, user, "login_locked", "master_karyawan", user["_id"],
               details={"email": user["email"], "minutes": LOGIN_LOCK_MINUTES})
    return True


def profile(user):
    """Data pengguna yang aman dikirim ke browser (tanpa password hash)."""
    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "role_label": ROLE_LABELS.get(user["role"], user["role"]),
        "must_change_password": bool(user.get("must_change_password")),
        "idle_timeout_minutes": IDLE_TIMEOUT_MINUTES,
    }


def change_password(db, user, data):
    """Pengguna mengganti password sendiri (wajib setelah akun dibuat atau password direset Admin, supaya
    Admin tidak mengetahui password siapa pun). Mengembalikan versi sesi yang baru."""
    from ..users.services import validate_password

    old = data.get("old_password")
    if not isinstance(old, str) or not check_password_hash(user["password_hash"], old):
        raise ValidationFailed("Password lama salah.", {"old_password": "Password lama salah."})
    new = validate_password(data.get("new_password"), "new_password")
    if new == old:
        raise ValidationFailed("Password baru harus berbeda dengan password lama.",
                               {"new_password": "Sama dengan password lama."})
    updated = db.master_karyawan.find_one_and_update(
        {"_id": user["_id"]},
        {"$set": {"password_hash": generate_password_hash(new), "must_change_password": False,
                  "failed_logins": 0, "locked_until": None, "updated_at": datetime.now(timezone.utc)},
         "$inc": {"session_version": 1}},  # sesi lain milik akun ini (perangkat lain) ikut berakhir
        return_document=ReturnDocument.AFTER)
    log_action(db, user, "password_changed", "master_karyawan", user["_id"])
    return updated
