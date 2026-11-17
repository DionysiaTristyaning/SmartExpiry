"""Titik masuk untuk Vercel (Vercel mencari objek Flask bernama `app` di file ini).

Menjalankan di komputer sendiri tetap memakai `py main.py`; file ini hanya untuk Vercel.
Bila pengaturan wajib (SECRET_KEY, MONGO_URI) belum diisi di Vercel, yang tampil adalah pesan yang jelas,
bukan layar error yang membingungkan."""
from flask import Flask

from app import create_app
from app.config import Config, missing_settings

app = Flask(__name__)  # dasar (terbaca oleh Vercel); diganti dengan aplikasi sebenarnya di bawah

_missing = missing_settings(Config)

if _missing:
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def not_configured(path):
        return (
            "Aplikasi belum bisa dijalankan: pengaturan " + ", ".join(_missing) + " belum diisi. "
            "Buka Vercel > Project > Settings > Environment Variables, isi pengaturan itu, lalu Redeploy.",
            500,
        )
else:
    app = create_app()
