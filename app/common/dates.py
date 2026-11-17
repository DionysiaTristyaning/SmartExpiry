"""Tanggal bisnis memakai zona waktu Asia/Jakarta (WIB = UTC+7, tanpa perubahan musim)."""
import re
from datetime import date, datetime, time, timedelta, timezone

from .errors import ValidationFailed

JAKARTA = timezone(timedelta(hours=7), "WIB")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today_jakarta():
    return datetime.now(JAKARTA).date()


def parse_iso_date(value, field, label):
    """Terima teks 'YYYY-MM-DD' yang valid. Mengembalikan objek date."""
    text = value.strip() if isinstance(value, str) else ""
    if not _ISO_DATE.match(text):
        raise ValidationFailed(f"{label} harus berformat TAHUN-BULAN-TANGGAL (contoh 2026-11-30).",
                               {field: "Format tanggal salah (YYYY-MM-DD)."})
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValidationFailed(f"{label} bukan tanggal yang valid.", {field: "Tanggal tidak valid."})


def parse_date_range(args):
    """Filter ?date_from=&date_to= (tanggal WIB, keduanya opsional). Mengembalikan (date|None, date|None)."""
    start = parse_iso_date(args.get("date_from"), "date_from", "Tanggal awal") if args.get("date_from") else None
    end = parse_iso_date(args.get("date_to"), "date_to", "Tanggal akhir") if args.get("date_to") else None
    if start and end and end < start:
        raise ValidationFailed("Tanggal akhir tidak boleh sebelum tanggal awal.", {"date_to": "Sebelum tanggal awal."})
    return start, end


def utc_bounds(start, end):
    """Ubah rentang tanggal WIB menjadi batas waktu UTC (tanpa zona) untuk query field waktu."""
    query = {}
    if start:
        query["$gte"] = datetime.combine(start, time.min, JAKARTA).astimezone(timezone.utc).replace(tzinfo=None)
    if end:
        query["$lt"] = datetime.combine(end + timedelta(days=1), time.min, JAKARTA).astimezone(timezone.utc).replace(tzinfo=None)
    return query


def iso_bounds(start, end):
    """Rentang untuk field tanggal teks 'YYYY-MM-DD'."""
    query = {}
    if start:
        query["$gte"] = start.isoformat()
    if end:
        query["$lte"] = end.isoformat()
    return query
