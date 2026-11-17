"""Membaca file CSV dengan aman (SD 9.4). Isi file TIDAK PERNAH dijalankan sebagai kode dan tidak disimpan ke disk."""
import csv
import hashlib
import io

from ...common.errors import ValidationFailed

MAX_BYTES = 1024 * 1024  # 1 MB
MAX_ROWS = 1000


def read_csv(upload, expected_headers, required_headers):
    """Baca file unggahan. Mengembalikan (daftar baris, sidik jari SHA-256 file).

    Tiap baris: (nomor_baris, dict_atau_None, pesan_error_atau_None). Kesalahan tingkat file (bukan CSV,
    terlalu besar, header salah) langsung ditolak dengan ValidationFailed.
    """
    if upload is None or not upload.filename:
        raise ValidationFailed("Pilih file dulu.")
    if not upload.filename.lower().endswith(".csv"):
        raise ValidationFailed("File harus berjenis .csv (di Excel: Save As, pilih 'CSV UTF-8').")

    raw = upload.stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationFailed("File terlalu besar (paling besar 1 MB). Bagi menjadi beberapa file.")
    if not raw.strip():
        raise ValidationFailed("File kosong.")
    if b"\x00" in raw:
        raise ValidationFailed("File tidak bisa dibaca. Pakai file contoh, isi di Excel, lalu simpan sebagai 'CSV UTF-8'.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationFailed("Jenis file belum benar. Di Excel pilih File > Save As, lalu pilih jenis 'CSV UTF-8'.")
    fingerprint = hashlib.sha256(raw).hexdigest()

    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=","))
    except csv.Error:
        raise ValidationFailed("File rusak dan tidak bisa dibaca.")
    if not rows:
        raise ValidationFailed("File kosong.")

    header = [cell.strip().lower() for cell in rows[0]]
    if len(set(header)) != len(header):
        raise ValidationFailed("Ada judul kolom yang ganda di baris pertama file.")
    missing = [name for name in required_headers if name not in header]
    unknown = [name for name in header if name not in expected_headers]
    if missing or unknown:
        parts = []
        if missing:
            parts.append("kolom yang kurang: " + ", ".join(missing))
        if unknown:
            parts.append("kolom tidak dikenal: " + ", ".join(unknown))
        raise ValidationFailed("Judul kolom di baris pertama tidak sama dengan file contoh (" + "; ".join(parts) + "). "
                               "Pakai file contoh, dan pastikan pemisah kolomnya koma (,).")

    result = []
    for number, cells in enumerate(rows[1:], start=2):  # baris 1 = header, seperti di Excel
        if not any(cell.strip() for cell in cells):
            continue  # lewati baris kosong
        if len(result) >= MAX_ROWS:
            raise ValidationFailed(f"Isi file terlalu banyak (paling banyak {MAX_ROWS} baris). Bagi menjadi beberapa file.")
        if len(cells) != len(header):
            result.append((number, None, "Jumlah kolom di baris ini tidak sama dengan judul kolom."))
        else:
            row = {name: "" for name in expected_headers}
            row.update(dict(zip(header, (cell.strip() for cell in cells))))
            result.append((number, row, None))
    if not result:
        raise ValidationFailed("File hanya berisi judul kolom, belum ada datanya.")
    return result, fingerprint
