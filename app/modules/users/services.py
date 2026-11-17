"""Manajemen akun (khusus Admin, SD 4.1 dan FR-USR).

Aturan:
- Akun tidak pernah dihapus, hanya dinonaktifkan. Email unik dan tidak dapat diubah.
- Admin tidak dapat menonaktifkan akunnya sendiri atau mengubah perannya sendiri.
- Admin aktif terakhir tidak dapat dinonaktifkan atau diturunkan perannya (sistem tidak boleh kehilangan Admin).
"""
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError
from werkzeug.security import generate_password_hash

from ...common.audit import log_action
from ...common.constants import ROLE_ADMIN, ROLES
from ...common.errors import Conflict, NotFound, ValidationFailed
from ...common.http import clean_email, clean_text, parse_enum

MIN_PASSWORD = 8
MAX_PASSWORD = 128


def validate_password(value, field="password"):
    if not isinstance(value, str) or not (MIN_PASSWORD <= len(value) <= MAX_PASSWORD):
        raise ValidationFailed(f"Password harus {MIN_PASSWORD}-{MAX_PASSWORD} karakter.",
                               {field: f"Password harus {MIN_PASSWORD}-{MAX_PASSWORD} karakter."})
    return value


def _is_last_active_admin(db, user):
    if user["role"] != ROLE_ADMIN or not user.get("is_active"):
        return False
    return db.master_karyawan.count_documents({"role": ROLE_ADMIN, "is_active": True}) <= 1


def list_users(db, filters, skip, limit, sort):
    query = {}
    if filters.get("role"):
        query["role"] = parse_enum(filters["role"], ROLES, "role", "Peran")
    if filters.get("is_active") in ("true", "false"):
        query["is_active"] = filters["is_active"] == "true"
    total = db.master_karyawan.count_documents(query)
    return [mark_locked(u) for u in db.master_karyawan.find(query).sort(sort).skip(skip).limit(limit)], total


def mark_locked(user):
    """Tambahkan berapa menit lagi akun ini terkunci (0 = tidak terkunci), untuk ditampilkan ke Admin."""
    from ..auth.services import locked_minutes_left

    user["locked_minutes"] = locked_minutes_left(user)
    return user


def get_user(db, user_id):
    user = db.master_karyawan.find_one({"_id": user_id})
    if not user:
        raise NotFound("Pengguna tidak ditemukan.")
    return mark_locked(user)


def create_user(db, actor, data):
    name = clean_text(data, "name", "Nama", max_len=80)
    if len(name) < 2:
        raise ValidationFailed("Nama minimal 2 karakter.", {"name": "Minimal 2 karakter."})
    email = clean_email(data)
    password = validate_password(data.get("password"))
    role = parse_enum(data.get("role"), ROLES, "role", "Peran")

    if db.master_karyawan.find_one({"email": email}):
        raise Conflict("Email sudah terdaftar.", {"email": "Email sudah terdaftar."})

    now = datetime.now(timezone.utc)
    doc = {
        "name": name, "email": email, "password_hash": generate_password_hash(password), "role": role,
        "is_active": True, "must_change_password": True, "last_login_at": None, "created_at": now, "updated_at": now, "created_by": actor["_id"],
    }
    try:
        doc["_id"] = db.master_karyawan.insert_one(doc).inserted_id
    except DuplicateKeyError:
        raise Conflict("Email sudah terdaftar.", {"email": "Email sudah terdaftar."})
    log_action(db, actor, "user_created", "master_karyawan", doc["_id"], details={"email": email, "role": role})
    return doc


def update_user(db, actor, user_id, data):
    """Yang dapat diubah: nama dan peran. Email tetap."""
    user = get_user(db, user_id)
    name = clean_text(data, "name", "Nama", max_len=80)
    if len(name) < 2:
        raise ValidationFailed("Nama minimal 2 karakter.", {"name": "Minimal 2 karakter."})
    role = parse_enum(data.get("role"), ROLES, "role", "Peran")
    if role != user["role"]:
        if user["_id"] == actor["_id"]:
            raise ValidationFailed("Anda tidak dapat mengubah peran akun Anda sendiri.", {"role": "Tidak diizinkan."})
        if _is_last_active_admin(db, user):
            raise ValidationFailed("Ini Admin aktif terakhir. Buat atau aktifkan Admin lain dulu sebelum mengubah perannya.",
                                   {"role": "Admin aktif terakhir."})

    changes = {"name": name, "role": role, "updated_at": datetime.now(timezone.utc)}
    db.master_karyawan.update_one({"_id": user_id}, {"$set": changes})
    log_action(db, actor, "user_updated", "master_karyawan", user_id,
               details={"old_role": user["role"], "new_role": role, "name_changed": name != user["name"]})
    return get_user(db, user_id)


def set_active(db, actor, user_id, active):
    user = get_user(db, user_id)
    if not active:
        if user["_id"] == actor["_id"]:
            raise ValidationFailed("Anda tidak dapat menonaktifkan akun Anda sendiri.")
        if _is_last_active_admin(db, user):
            raise ValidationFailed("Ini Admin aktif terakhir dan tidak dapat dinonaktifkan.")
    db.master_karyawan.update_one({"_id": user_id}, {"$set": {"is_active": active, "updated_at": datetime.now(timezone.utc)}})
    log_action(db, actor, "user_activated" if active else "user_deactivated", "master_karyawan", user_id)
    return get_user(db, user_id)


def reset_password(db, actor, user_id, data):
    """Admin mengatur password baru. Password disampaikan ke pengguna di luar aplikasi (SD 12).
    Kunci login sementara (karena salah password berkali-kali) ikut dibuka. Pengguna WAJIB mengganti password ini
    saat masuk berikutnya, sehingga Admin tidak mengetahui password yang dipakai sehari-hari.
    Semua sesi pengguna itu yang masih login ikut berakhir. Bila Admin mengatur ulang passwordnya sendiri,
    Admin juga harus login ulang."""
    get_user(db, user_id)
    password = validate_password(data.get("new_password"), "new_password")
    # session_version naik: semua sesi yang sedang login dengan password lama langsung tidak berlaku
    db.master_karyawan.update_one({"_id": user_id}, {"$set": {"password_hash": generate_password_hash(password),
                                                     "updated_at": datetime.now(timezone.utc),
                                                     "failed_logins": 0, "locked_until": None,
                                                     "must_change_password": True},
                                            "$inc": {"session_version": 1}})
    log_action(db, actor, "user_password_reset", "master_karyawan", user_id)
    return get_user(db, user_id)
