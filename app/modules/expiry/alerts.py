"""Daftar monitoring (SD 5.4): batch Monitoring, Critical, dan Expired yang stoknya > 0,
diurutkan dari sisa hari terkecil. Batch yang stoknya 0 tidak dipantau lagi.

Tampilan khusus status=check_due: batch yang sudah waktunya dicek fisik menurut jadwal (SD 5.5 A),
paling mendesak di atas (Critical dulu, lalu yang paling lama belum dicek)."""
from datetime import timedelta

from ...common.constants import MONITORING_DAYS
from ...common.dates import today_jakarta
from ...common.http import parse_enum, parse_object_id
from ..batches import services as batch_services
from . import services as expiry

ALERT_STATUSES = ("monitoring", "critical", "expired")


def alert_query(filters, today):
    query = {"current_quantity": {"$gt": 0}}
    status = filters.get("status")
    if status:
        parse_enum(status, ALERT_STATUSES, "status", "Status")
        query["expiry_date"] = expiry.expiry_date_filter(status, today)
    else:  # semua status pantauan = sisa hari <= batas Monitoring
        query["expiry_date"] = {"$lte": (today + timedelta(days=MONITORING_DAYS)).isoformat()}
    if filters.get("product_id"):
        query["product_id"] = parse_object_id(filters["product_id"], "product_id")
    return query


STATUS_RANK = {"critical": 0, "monitoring": 1, "normal": 2}


def due_for_check(db, today=None, product_id=None):
    """Semua batch yang sudah waktunya dicek fisik (dihitung saat diminta)."""
    today = today or today_jakarta()
    query = {"current_quantity": {"$gt": 0}, "expiry_date": expiry.not_expired_filter(today)}
    if product_id:
        query["product_id"] = product_id
    items = [b for b in batch_services.enrich(db, list(db.batches.find(query)), today) if b["check_due"]]
    items.sort(key=lambda b: (STATUS_RANK[b["expiry_status"]], -b["days_since_check"], b["expiry_date"]))
    return items


def list_alerts(db, filters, skip, limit):
    today = today_jakarta()
    if filters.get("status") == "check_due":
        product_id = parse_object_id(filters["product_id"], "product_id") if filters.get("product_id") else None
        items = due_for_check(db, today, product_id)
        return items[skip:skip + limit], len(items)
    query = alert_query(filters, today)
    total = db.batches.count_documents(query)
    items = list(db.batches.find(query).sort([("expiry_date", 1), ("batch_number", 1)]).skip(skip).limit(limit))
    return batch_services.enrich(db, items, today), total
