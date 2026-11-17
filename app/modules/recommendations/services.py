"""Rekomendasi dihitung SETIAP kali diminta dari data terbaru; tidak disimpan di database (SD 5.5 B).

Catatan skala: seluruh batch ber-stok dihitung lalu diurutkan di memori. Ini cukup untuk satu outlet
(ratusan sampai ribuan batch).
"""
from collections import defaultdict

from ...common.dates import today_jakarta
from ...common.errors import NotFound
from ...common.http import parse_enum, parse_object_id
from ..batches import services as batch_services
from .rules import ACTIONS, recommend

OPEN_REQUEST_STATUSES = ("pending", "approved")


def _decorate(db, batches):
    """Hitung urutan FEFO, rekomendasi, dan jumlah pengajuan yang masih terbuka."""
    today = today_jakarta()
    batch_services.enrich(db, batches, today)

    # Urutan FEFO dalam satu produk: batch ber-stok yang belum Expired, kedaluwarsa terdekat = nomor 1
    groups = defaultdict(list)
    for batch in db.batches.find({"product_id": {"$in": list({b["product_id"] for b in batches})},
                                  "current_quantity": {"$gt": 0}, "expiry_date": {"$gt": today.isoformat()}},
                                 {"product_id": 1, "expiry_date": 1, "batch_number": 1}):
        groups[batch["product_id"]].append(batch)
    rank = {}
    for items in groups.values():
        items.sort(key=lambda b: (b["expiry_date"], b["batch_number"]))
        for position, item in enumerate(items, start=1):
            rank[item["_id"]] = (position, len(items))

    open_counts = defaultdict(int)
    for req in db.handling_requests.find({"batch_id": {"$in": [b["_id"] for b in batches]},
                                          "status": {"$in": list(OPEN_REQUEST_STATUSES)}}, {"batch_id": 1}):
        open_counts[req["batch_id"]] += 1

    for batch in batches:
        position, total = rank.get(batch["_id"], (None, None))
        batch["fefo_rank"], batch["fefo_total"] = position, total
        batch.update(recommend(batch))
        batch["open_request_count"] = open_counts.get(batch["_id"], 0)
    return batches


def list_recommendations(db, filters, skip, limit):
    action = filters.get("action")
    if action:
        parse_enum(action, tuple(ACTIONS), "action", "Jenis saran")
    query = {"current_quantity": {"$gt": 0}}  # batch tanpa stok tidak perlu rekomendasi
    if filters.get("product_id"):
        query["product_id"] = parse_object_id(filters["product_id"], "product_id")
    batches = _decorate(db, list(db.batches.find(query)))
    if action:
        batches = [b for b in batches if b["action"] == action]
    batches.sort(key=lambda b: (b["priority"], b["remaining_days"], b["batch_number"]))
    return batches[skip:skip + limit], len(batches)


def get_recommendation(db, batch_id):
    batch = db.batches.find_one({"_id": batch_id})
    if not batch:
        raise NotFound("Kiriman tidak ditemukan.")
    if batch["current_quantity"] <= 0:
        raise NotFound("Kiriman ini tidak memiliki stok, sehingga tidak ada saran.")
    return _decorate(db, [batch])[0]
