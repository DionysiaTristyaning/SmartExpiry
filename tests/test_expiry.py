"""Status kedaluwarsa (SD 5.4, 13.3 E1-E3)."""
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import pytest

from app.common import dates
from app.modules.expiry import services as expiry
from tests.conftest import STAFF


@pytest.mark.parametrize("days,status", [
    (365, "normal"), (91, "normal"), (90, "monitoring"), (60, "monitoring"), (31, "monitoring"),
    (30, "critical"), (14, "critical"), (7, "critical"), (1, "critical"), (0, "expired"), (-1, "expired"), (-30, "expired"),
])
def test_status_boundaries_do_not_overlap(days, status):
    today = date(2026, 11, 12)
    assert expiry.compute((today + timedelta(days=days)).isoformat(), today) == \
        {"remaining_days": days, "expiry_status": status}


def test_expiry_date_today_is_expired_not_critical():
    today = date(2026, 11, 20)
    assert expiry.status_for_days(expiry.remaining_days("2026-11-20", today)) == "expired"
    assert expiry.status_for_days(expiry.remaining_days("2026-11-20", date(2026, 11, 19))) == "critical"


@pytest.mark.parametrize("status", expiry.STATUSES)
def test_date_filter_matches_status_function(status):
    today = date(2026, 11, 12)
    rng = expiry.expiry_date_filter(status, today)
    for days in range(-5, 40):
        iso = (today + timedelta(days=days)).isoformat()
        inside = all({"$gt": iso > v, "$lte": iso <= v}[op] for op, v in rng.items())
        assert inside == (expiry.status_for_days(days) == status), (status, days)


def test_business_date_uses_jakarta_time():
    # 23.30 WIB tanggal 12 = 16.30 UTC tanggal 12; 01.00 WIB tanggal 13 = 18.00 UTC tanggal 12
    with mock.patch.object(dates, "datetime", wraps=datetime) as fake:
        fake.now.side_effect = lambda tz=None: datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc).astimezone(tz)
        assert dates.today_jakarta() == date(2026, 11, 13)


def test_batches_with_zero_stock_are_not_monitored(login_as, db):
    db.batches.update_many({}, {"$set": {"current_quantity": 0}})
    data = login_as(STAFF).get("/api/v1/expiry/alerts").get_json()
    assert data["total"] == 0
    summary = login_as(STAFF).get("/api/v1/dashboard/summary").get_json()["data"]
    assert sum(summary["by_status"].values()) == 0 and summary["total_available_stock"] == 0


def test_alerts_are_sorted_nearest_first_and_exclude_normal(login_as):
    items = login_as(STAFF).get("/api/v1/expiry/alerts?limit=100").get_json()["data"]
    assert items and all(i["expiry_status"] != "normal" and i["current_quantity"] > 0 for i in items)
    assert [i["expiry_date"] for i in items] == sorted(i["expiry_date"] for i in items)


def test_alert_status_filter(login_as):
    c = login_as(STAFF)
    for status in ("monitoring", "critical", "expired"):
        items = c.get(f"/api/v1/expiry/alerts?status={status}").get_json()["data"]
        assert all(i["expiry_status"] == status for i in items)
    assert c.get("/api/v1/expiry/alerts?status=normal").status_code == 400


def test_status_is_never_stored(db):
    assert db.batches.count_documents({"expiry_status": {"$exists": True}}) == 0
    assert db.batches.count_documents({"remaining_days": {"$exists": True}}) == 0
