"""Pembantu untuk membaca request dan membentuk response JSON."""
import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import jsonify, request

from .errors import ValidationFailed

HIDDEN_FIELDS = {"password_hash"}


def ok(data=None, status=200, **extra):
    body = {"data": serialize(data)}
    body.update(extra)
    return jsonify(body), status


def fail(message, status=400, fields=None):
    return jsonify({"error": {"message": message, "fields": fields or {}}}), status


def serialize(value):
    """Ubah ObjectId -> str, datetime -> teks ISO, dan buang field rahasia."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in HIDDEN_FIELDS:
                continue
            result["id" if key == "_id" else key] = serialize(item)
        return result
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    return value


def json_body():
    """Ambil body JSON; harus berupa objek (dict)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationFailed("Isian tidak bisa dibaca. Muat ulang halaman (tekan F5) lalu coba lagi.")
    return data


def parse_object_id(value, field="id"):
    if not isinstance(value, str):
        raise ValidationFailed("ID tidak valid.", {field: "ID tidak valid."})
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise ValidationFailed("ID tidak valid.", {field: "ID tidak valid."})


def page_args(allowed_sort, default_sort):
    """Baca ?page=&limit=&sort= dengan batas aman. sort hanya boleh field yang diizinkan."""
    try:
        page = max(int(request.args.get("page", 1)), 1)
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except ValueError:
        raise ValidationFailed("Parameter halaman tidak valid.")
    sort_value = request.args.get("sort", default_sort)
    descending = sort_value.startswith("-")
    field = sort_value.lstrip("-")
    if field not in allowed_sort:
        raise ValidationFailed("Parameter sort tidak diizinkan.")
    direction = -1 if descending else 1
    return (page - 1) * limit, limit, [(field, direction)]


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def clean_text(data, field, label, max_len=100, required=True):
    """Ambil teks satu baris: harus string, dirapikan, tanpa karakter kontrol, dibatasi panjangnya."""
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationFailed(f"{label} wajib diisi.", {field: f"{label} wajib diisi."})
        return ""
    if not isinstance(value, str):
        raise ValidationFailed(f"{label} tidak valid.", {field: f"{label} tidak valid."})
    value = value.strip()
    if value[:1] in ("=", "+", "@") or (value[:1] == "-" and value[1:2] != " "):
        # Mencegah "formula injection" jika data nanti dibuka di Excel (SD 12). Tanda "-" yang diikuti spasi
        # (gaya daftar, misalnya "- 2 unit penyok") tetap boleh karena tidak dibaca Excel sebagai rumus.
        raise ValidationFailed(f"{label} tidak boleh diawali tanda = + @, atau tanda - yang langsung diikuti "
                               "huruf/angka.", {field: "Jangan diawali = + @ atau - tanpa spasi."})
    if "<" in value or ">" in value:
        # Sanitasi: tanda < dan > ditolak agar teks tidak bisa menyisipkan tag HTML/script
        # (daftar pilihan Webix menampilkan teks sebagai HTML).
        raise ValidationFailed(f"{label} tidak boleh mengandung tanda < atau >.",
                               {field: "Tanda < dan > tidak diizinkan."})
    if _CONTROL_CHARS.search(value):
        raise ValidationFailed(f"{label} berisi simbol yang tidak boleh dipakai.",
                               {field: "Ada simbol yang tidak boleh dipakai."})
    if len(value) > max_len:
        raise ValidationFailed(f"{label} terlalu panjang (paling banyak {max_len} huruf).",
                               {field: f"Maksimal {max_len} karakter."})
    return value


def parse_quantity(value, field, label, max_value=1_000_000, minimum=1):
    """Jumlah harus bilangan bulat (default: lebih dari 0). Menerima angka atau teks angka (dari CSV)."""
    if isinstance(value, bool):
        value = None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int) or value < minimum:
        text = "lebih dari 0" if minimum == 1 else "0 atau lebih"
        raise ValidationFailed(f"{label} harus diisi angka bulat {text}.", {field: f"Isi angka bulat {text}."})
    if value > max_value:
        raise ValidationFailed(f"{label} terlalu besar (paling banyak {max_value}).",
                               {field: f"Maksimal {max_value}."})
    return value


def clean_email(data, field="email"):
    value = clean_text(data, field, "Email", max_len=120).lower()
    if not _EMAIL.match(value):
        raise ValidationFailed("Penulisan email belum benar (contoh: nama@gmail.com).", {field: "Contoh: nama@gmail.com"})
    return value


_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def parse_client_request_id(data):
    """ID unik dari form (dibuat browser saat form dibuka). Kiriman ulang dengan ID yang sama ditolak (SD 7.9)."""
    value = data.get("client_request_id")
    if not isinstance(value, str) or not _UUID.match(value):
        raise ValidationFailed("Form ini perlu dibuka ulang. Tutup, lalu buka lagi.",
                               {"client_request_id": "ID form tidak valid."})
    return value.lower()


def parse_enum(value, allowed, field, label, required=True):
    if value in (None, "") and not required:
        return None
    if value not in allowed:
        raise ValidationFailed(f"{label} tidak valid.", {field: f"{label} tidak valid."})
    return value
