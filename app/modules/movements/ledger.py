"""Buku besar stok: SATU-SATUNYA tempat `current_quantity` batch diubah (SD 8.9).

Aturan:
- Stok berubah hanya dengan mencatat pergerakan (stok masuk, stok keluar, penyesuaian naik/turun).
- Pengurangan memakai pembaruan bersyarat (`current_quantity >= jumlah`), jadi stok tidak pernah negatif,
  walaupun dua pengguna mengurangi stok bersamaan.
- Pembaruan batch dan pencatatan pergerakan berjalan dalam satu transaksi. Di database tiruan (tes) yang tidak
  mendukung transaksi, perubahan stok dibatalkan secara manual bila pencatatan gagal.
- Setiap pergerakan menyimpan sumbernya (`source`): manual, csv_import, inspection, atau handling_request.
"""
from datetime import datetime, timezone

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...common.errors import Conflict, ValidationFailed

MOVEMENT_TYPES = ("stock_in", "stock_out", "adjustment_in", "adjustment_out")
INCREASE_TYPES = ("stock_in", "adjustment_in")
MOVEMENT_LABELS = {
    "stock_in": "Stok Masuk",
    "stock_out": "Stok Keluar",
    "adjustment_in": "Stok disamakan (+)",
    "adjustment_out": "Stok disamakan (-)",
}

DUPLICATE_MESSAGE = "Data ini sudah tersimpan (tombol tertekan dua kali). Tidak ada data ganda."


def ensure_new_client_request(db, client_request_id, session=None):
    if client_request_id and db.stock_movements.find_one({"client_request_id": client_request_id}, {"_id": 1},
                                                         session=session):
        raise Conflict(DUPLICATE_MESSAGE)


def record_movement(db, batch, actor, movement_type, quantity, *, movement_date, source,
                    reason=None, notes="", client_request_id=None, expected_quantity=None, reserve=0, session=None, now=None):
    """Ubah stok batch secara atomik lalu catat pergerakannya. Mengembalikan dokumen pergerakan.

    expected_quantity: bila diisi, stok batch harus PERSIS sebesar itu (dipakai penyesuaian dari pemeriksaan,
    supaya selisih yang sudah usang tidak diterapkan).
    reserve: stok yang harus TETAP tersisa setelah pengurangan (barang rusak yang belum ditangani tidak boleh
    ikut "terjual").
    """
    if movement_type not in MOVEMENT_TYPES:
        raise ValidationFailed("Jenis pergerakan tidak valid.")
    now = now or datetime.now(timezone.utc)
    delta = quantity if movement_type in INCREASE_TYPES else -quantity

    condition = {"_id": batch["_id"]}
    if expected_quantity is not None:
        condition["current_quantity"] = expected_quantity
    elif delta < 0:
        condition["current_quantity"] = {"$gte": quantity + reserve}
    updated = db.batches.find_one_and_update(
        condition, {"$inc": {"current_quantity": delta}, "$set": {"updated_at": now}},
        return_document=ReturnDocument.AFTER, session=session)
    if updated is None:
        current = (db.batches.find_one({"_id": batch["_id"]}, {"current_quantity": 1}, session=session) or {})
        if expected_quantity is not None:
            raise Conflict("Stok berubah sejak pemeriksaan; lakukan pemeriksaan ulang.")
        left = max(0, current.get("current_quantity", 0) - reserve)
        raise ValidationFailed(f"Jumlah melebihi stok kiriman (tersisa {left}).",
                               {"quantity": "Melebihi stok kiriman."})

    after = updated["current_quantity"]
    movement = {
        "batch_id": batch["_id"],
        "product_id": batch["product_id"],
        "movement_type": movement_type,
        "quantity": quantity,
        "quantity_before": after - delta,
        "quantity_after": after,
        "movement_date": movement_date,
        "reason": reason,
        "notes": notes or "",
        "source": source,
        "created_by": actor["_id"] if actor else None,
        "created_at": now,
    }
    if client_request_id:
        movement["client_request_id"] = client_request_id
    try:
        movement["_id"] = db.stock_movements.insert_one(movement, session=session).inserted_id
    except DuplicateKeyError:
        if session is None:  # tanpa transaksi: kembalikan stok secara manual
            db.batches.update_one({"_id": batch["_id"]}, {"$inc": {"current_quantity": -delta}})
        raise Conflict(DUPLICATE_MESSAGE)
    return movement
