"""Nomor dokumen yang dibuat sistem: PREFIX-YYMMDD-NNN (contoh BT-261112-003).

Nomor urut dihitung per tanggal. Keunikannya dijaga indeks unik di database: bila dua pengguna menyimpan
bersamaan dan mendapat nomor yang sama, penyimpanan kedua gagal lalu diulang dengan nomor berikutnya.
"""
import re

MAX_ATTEMPTS = 5


def prefix_for(code, day):
    return f"{code}-{day:%y%m%d}-"


def next_number(db, collection, field, prefix, taken=None, session=None):
    """Nomor berikutnya untuk prefix ini. `taken` = nomor yang sudah dipakai di memori (impor massal)."""
    last = 0
    pattern = {"$regex": "^" + re.escape(prefix)}
    for doc in db[collection].find({field: pattern}, {field: 1}, session=session):
        tail = doc[field][len(prefix):]
        if tail.isdigit():
            last = max(last, int(tail))
    for value in taken or ():
        tail = value[len(prefix):] if value.startswith(prefix) else ""
        if tail.isdigit():
            last = max(last, int(tail))
    return f"{prefix}{last + 1:03d}"
