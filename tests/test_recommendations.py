"""Rekomendasi berbasis aturan (SD 5.5 B, 13.3 R1-R3)."""
from datetime import datetime, timezone

import pytest

from app.modules.recommendations.rules import ACTIONS, recommend
from tests.conftest import STAFF, batch_of

NOW = datetime(2026, 11, 12, tzinfo=timezone.utc)


def _b(status, days, last=None, rank=None, total=None):
    damaged = 2 if last and not last["is_fit"] else 0
    return {"expiry_status": status, "remaining_days": days, "last_inspection": last, "fefo_rank": rank,
            "fefo_total": total, "damaged_quantity": damaged, "current_quantity": 10}


def _insp(fit, product="baik", packaging="baik"):
    return {"is_fit": fit, "product_condition": product, "packaging_condition": packaging, "inspected_at": NOW}


@pytest.mark.parametrize("batch,action", [
    (_b("expired", 0), "withdraw"),
    (_b("expired", -3, _insp(False, "rusak")), "withdraw"),          # Expired lebih dulu daripada rusak
    (_b("critical", 3, _insp(False, packaging="rusak")), "separate"),  # rusak lebih dulu daripada Critical
    (_b("normal", 90, _insp(False, "rusak")), "separate"),
    (_b("critical", 3), "prioritize_handling"),
    (_b("critical", 3, _insp(True)), "prioritize_handling"),
    (_b("near_expired", 10), "prioritize_sale"),
    (_b("monitoring", 20), "monitor_fefo"),
    (_b("normal", 45), "no_action"),
])
def test_rule_order(batch, action):
    assert recommend(batch)["action"] == action


def test_no_discount_anywhere():
    labels = " ".join(label for _, label, _ in ACTIONS.values()).lower()
    assert "diskon" not in labels
    for status, days in (("critical", 3), ("near_expired", 10), ("expired", 0)):
        assert "diskon" not in recommend(_b(status, days))["reason"].lower()


def test_critical_not_inspected_asks_for_inspection():
    assert "lakukan pemeriksaan fisik" in recommend(_b("critical", 2))["reason"].lower()
    assert "layak" in recommend(_b("critical", 2, _insp(True)))["reason"].lower()


def test_only_withdraw_and_separate_need_a_request():
    assert {k for k, (_, _, needs) in ACTIONS.items() if needs} == {"withdraw", "separate"}


def test_api_gives_one_recommendation_per_stocked_batch_with_reason(login_as, db):
    data = login_as(STAFF).get("/api/v1/recommendations?limit=100").get_json()
    stocked = db.batches.count_documents({"current_quantity": {"$gt": 0}})
    assert data["total"] == stocked
    assert all(i["reason"] and i["action"] in ACTIONS for i in data["data"])
    priorities = [i["priority"] for i in data["data"]]
    assert priorities == sorted(priorities)


def test_api_seed_examples(login_as, db):
    c = login_as(STAFF)
    expired = c.get(f"/api/v1/recommendations/{batch_of(db, 'P013')['_id']}").get_json()["data"]
    assert expired["action"] == "withdraw" and expired["open_request_count"] == 1
    damaged = c.get(f"/api/v1/recommendations/{batch_of(db, 'P005')['_id']}").get_json()["data"]
    assert damaged["action"] == "separate"


def test_fefo_rank_within_product(login_as, db):
    items = login_as(STAFF).get("/api/v1/recommendations?limit=100").get_json()["data"]
    susu = sorted([i for i in items if i["sku"] == "P001"], key=lambda i: i["expiry_date"])
    assert [i["fefo_rank"] for i in susu] == [1, 2] and all(i["fefo_total"] == 2 for i in susu)


def test_recommendations_change_nothing(login_as, db):
    counts = {name: db[name].count_documents({}) for name in ("stock_movements", "handling_requests", "batches")}
    login_as(STAFF).get("/api/v1/recommendations?limit=100")
    assert counts == {name: db[name].count_documents({}) for name in counts}


def test_invalid_action_filter(login_as):
    assert login_as(STAFF).get("/api/v1/recommendations?action=review_discount").status_code == 400


def test_critical_suggests_return_before_it_is_too_late():
    assert "ajukan pengembalian ke pemasok selagi masih layak" in recommend(_b("critical", 3, _insp(True)))["reason"]


def test_partial_damage_says_the_rest_can_still_be_sold():
    reason = recommend(_b("normal", 90, _insp(False, "rusak")))["reason"]
    assert "2 unit yang rusak" in reason and "Sisanya (8 unit)" in reason
