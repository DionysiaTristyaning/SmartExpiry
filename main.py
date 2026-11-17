"""Titik masuk aplikasi. Jalankan dengan:  py main.py"""
import sys

from app import create_app
from app.config import Config, missing_settings, secret_key_warning
from app.db import check_connection
from app.indexes import ensure_indexes

HOST = "127.0.0.1"
PORT = 5000


def stop(message):
    print("\n" + "=" * 60)
    print(message)
    print("=" * 60 + "\n")
    sys.exit(1)


def main():
    missing = missing_settings(Config)
    if missing:
        stop(
            "File .env belum lengkap. Nilai berikut masih kosong: " + ", ".join(missing) + "\n"
            "Buka file .env lalu isi nilainya. Panduan lengkap ada di README.md."
        )

    warning = secret_key_warning(Config)
    if warning:
        print("\nPERINGATAN: " + warning + "\n")

    app = create_app()

    problem = check_connection(app.db)
    if problem:
        stop("Gagal terhubung ke database.\n" + problem)

    ensure_indexes(app.db)  # aman dijalankan berulang kali

    print(f"Aplikasi berjalan. Buka di browser: http://{HOST}:{PORT}")
    print("Tekan Ctrl+C untuk menghentikan.")
    # debug sengaja dimatikan: mode debug Flask membuka konsol interaktif yang berbahaya.
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
