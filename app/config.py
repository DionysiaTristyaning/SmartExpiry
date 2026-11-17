"""Konfigurasi aplikasi. Semua nilai rahasia dibaca dari file .env (bukan ditulis di kode)."""
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _bool(value, default=False):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class Config:
    ENV = os.getenv("FLASK_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    MONGO_URI = os.getenv("MONGO_URI", "")
    DATABASE_NAME = os.getenv("DATABASE_NAME") or "smart_expiry_db"
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH") or 2097152)  # 2 MB (SD 12)

    # Di Vercel (variabel VERCEL terisi otomatis) koneksi selalu HTTPS, jadi cookie otomatis "aman" bila tidak diatur.
    SESSION_COOKIE_SECURE = _bool(os.getenv("SESSION_COOKIE_SECURE"), bool(os.getenv("VERCEL")))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    WTF_CSRF_TIME_LIMIT = None  # token CSRF berlaku selama sesi


# Pengaturan yang wajib diisi sebelum aplikasi boleh jalan.
REQUIRED_SETTINGS = ("SECRET_KEY", "MONGO_URI")


MIN_SECRET_LENGTH = 32


def secret_key_warning(config=Config):
    """Peringatan (bukan error) jika SECRET_KEY terlalu pendek/mudah ditebak. None jika aman."""
    key = str(getattr(config, "SECRET_KEY", "")).strip()
    if key and len(key) < MIN_SECRET_LENGTH:
        return ("SECRET_KEY terlalu pendek (kurang dari 32 karakter) sehingga mudah ditebak. "
                "Buat yang baru dengan: py -c \"import secrets; print(secrets.token_hex(32))\"")
    return None


def missing_settings(config=Config):
    """Daftar nama pengaturan wajib yang masih kosong."""
    return [name for name in REQUIRED_SETTINGS if not str(getattr(config, name, "")).strip()]
