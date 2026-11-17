"""Koneksi MongoDB dan penjelasan error yang mudah dipahami."""
from pymongo import MongoClient
from pymongo.errors import (ConfigurationError, InvalidURI, OperationFailure,
                            ServerSelectionTimeoutError)


def create_database(uri, database_name):
    """Buat objek database. Koneksi sebenarnya baru dibuat saat dipakai pertama kali."""
    client = MongoClient(uri, serverSelectionTimeoutMS=8000, tz_aware=True)
    return client[database_name]


def check_connection(db):
    """Tes koneksi. Mengembalikan None jika berhasil, atau teks penjelasan jika gagal."""
    try:
        db.client.admin.command("ping")
        return None
    except (InvalidURI, ConfigurationError):
        return ("Format MONGO_URI salah. Salin ulang connection string dari MongoDB Atlas. "
                "Jika password mengandung simbol (@ : / ?), password itu harus di-encode atau diganti.")
    except OperationFailure as exc:
        if getattr(exc, "code", None) == 18 or "auth" in str(exc).lower():
            return ("Username atau password database salah. Periksa lagi 'Database Access' di MongoDB Atlas "
                    "dan isi MONGO_URI dengan password yang benar.")
        return f"MongoDB menolak permintaan: {exc.details.get('errmsg', 'tanpa keterangan') if exc.details else exc}"
    except ServerSelectionTimeoutError:
        return ("Tidak bisa terhubung ke MongoDB Atlas. Penyebab yang paling sering: alamat IP komputer ini "
                "belum didaftarkan di 'Network Access' Atlas, atau internet sedang bermasalah.")
    except Exception as exc:  # pragma: no cover - jaring pengaman
        return f"Koneksi database gagal: {type(exc).__name__}"
