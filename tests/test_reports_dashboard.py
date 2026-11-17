"""Dashboard, notifikasi, laporan, ekspor Excel, dan riwayat aktivitas (SD 5.1, 5.6, 13.5 L1-L3)."""
import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from app.common.xlsx import build_workbook
from app.modules.reports import services as report_services
from tests.conftest import ADMIN, STAFF, STAFF2, SUPERVISOR, batch_of, rid

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
KINDS = list(report_services.REPORTS)


def read_xlsx(content):
    z = zipfile.ZipFile(io.BytesIO(content))
    for name in z.namelist():
        ET.fromstring(z.read(name))  # semua bagian XML valid
    rows = []
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).find("m:sheetData", NS):
        values = []
        for c in row:
            values.append("".join(t.text or "" for t in c.iter("{%s}t" % NS["m"])) if c.get("t") == "inlineStr"
                          else float(c.find("m:v", NS).text))
        rows.append(values)
    return rows


# ---------- dashboard ----------

def test_dashboard_numbers_match_database(login_as, db):
    s = login_as(SUPERVISOR).get("/api/v1/dashboard/summary").get_json()["data"]
    assert s["total_active_products"] == db.master_product.count_documents({"is_active": True})
    assert sum(s["by_status"].values()) == db.batches.count_documents({"current_quantity": {"$gt": 0}})
    stocked = sum(b["current_quantity"] for b in db.batches.find({"current_quantity": {"$gt": 0}}))
    assert s["total_available_stock"] + s["expired_units"] + s["damaged_units"] == stocked
    assert s["damaged_units"] == 3  # roti: 3 bungkus rusak dari cek fisik di seed
    assert s["pending_requests"] == db.handling_requests.count_documents({"status": "pending"})
    assert s["low_stock_products"] == 3  # roti, sarden, jus
    assert s["recent_adjustments"] == 1 and s["pending_corrections"] == 1
    assert "approved_open_requests" not in s


def test_staff_dashboard_has_no_supervision_numbers(login_as):
    s = login_as(STAFF).get("/api/v1/dashboard/summary").get_json()["data"]
    assert "recent_adjustments" not in s and "pending_corrections" not in s and "low_stock_products" in s


def test_staff_dashboard_shows_approved_open_requests(login_as, db):
    s = login_as(STAFF).get("/api/v1/dashboard/summary").get_json()["data"]
    assert s["approved_open_requests"] == db.handling_requests.count_documents({"status": "approved"})


# ---------- notifikasi ----------

def test_supervisor_sees_requests_corrections_and_adjustments_but_not_low_stock(login_as):
    data = login_as(SUPERVISOR).get("/api/v1/notifications").get_json()["data"]
    assert {i["kind"] for i in data["items"]} == {"review_needed", "expiry_correction", "adjustment"}
    # stok menipis tetap ada di kartu dashboard dan laporan, tetapi bukan pemberitahuan lonceng
    assert login_as(SUPERVISOR).get("/api/v1/dashboard/summary").get_json()["data"]["low_stock_products"] == 3


def _recount(client, batch):
    body = {"batch_id": str(batch["_id"]), "physical_quantity": batch["current_quantity"], "product_condition": "baik",
            "packaging_condition": "baik", "damaged_quantity": 0, "expiry_label": "match", "notes": "",
            "client_request_id": rid()}
    return client.post("/api/v1/inspections", json=body)


def test_adjustment_notice_disappears_only_after_supervisor_rechecks(login_as, db):
    moved = db.stock_movements.find_one({"source.type": "inspection"})
    batch = db.batches.find_one({"_id": moved["batch_id"]})

    def adjustment_items(who):
        data = login_as(who).get("/api/v1/notifications").get_json()["data"]["items"]
        return [i for i in data if i["kind"] == "adjustment" and i["batch_id"] == str(batch["_id"])]

    assert adjustment_items(SUPERVISOR) and adjustment_items(ADMIN)
    assert _recount(login_as(STAFF2), batch).status_code == 201          # Staff mengecek lagi: belum dianggap pengawasan
    assert adjustment_items(SUPERVISOR) and adjustment_items(ADMIN)
    assert _recount(login_as(SUPERVISOR), batch).status_code == 201      # Supervisor mengecek fisik kiriman itu
    assert not adjustment_items(SUPERVISOR) and not adjustment_items(ADMIN)
    summary = login_as(SUPERVISOR).get("/api/v1/dashboard/summary").get_json()["data"]
    assert summary["recent_adjustments"] == 0                            # kartu dashboard ikut sama
    assert login_as(ADMIN).get("/api/v1/dashboard/summary").get_json()["data"]["recent_adjustments"] == 0
    rows = login_as(SUPERVISOR).get("/api/v1/reports/adjustments").get_json()["data"]
    assert len(rows) == 1                                                # riwayatnya tetap ada di laporan


def test_staff_sees_approved_and_own_rejections(login_as):
    staff1 = login_as(STAFF).get("/api/v1/notifications").get_json()["data"]["items"]
    kinds = {i["kind"] for i in staff1}
    assert kinds == {"approved", "rejected", "check_due"}  # staff1 pengaju yang ditolak di seed
    staff2 = login_as(STAFF2).get("/api/v1/notifications").get_json()["data"]["items"]
    assert {i["kind"] for i in staff2} == {"approved", "check_due"}  # penolakan milik orang lain tidak tampil


def test_admin_only_monitors_adjustments(login_as):
    items = login_as(ADMIN).get("/api/v1/notifications").get_json()["data"]["items"]
    assert items and {i["kind"] for i in items} == {"adjustment"}


def test_notifications_update_after_decision(login_as, db):
    staff = login_as(STAFF)
    response = staff.post("/api/v1/requests", json={"batch_id": str(batch_of(db, "P009")["_id"]), "request_type": "return",
                                                    "quantity": 1, "reason": "Kemasan penyok", "client_request_id": rid()})
    req_id = response.get_json()["data"]["id"]
    sup = login_as(SUPERVISOR)
    assert any(i.get("request_id") == req_id for i in sup.get("/api/v1/notifications").get_json()["data"]["items"])
    sup.post(f"/api/v1/requests/{req_id}/reject", json={"note": "Masih layak"})
    assert not any(i.get("request_id") == req_id for i in sup.get("/api/v1/notifications").get_json()["data"]["items"])
    assert any(i.get("request_id") == req_id and i["kind"] == "rejected"
               for i in staff.get("/api/v1/notifications").get_json()["data"]["items"])


# ---------- laporan ----------

@pytest.mark.parametrize("kind", KINDS)
def test_every_report_and_its_export(login_as, db, kind):
    c = login_as(SUPERVISOR)
    data = c.get(f"/api/v1/reports/{kind}?limit=100").get_json()
    assert "summary" in data and "generated_at" in data and data["total"] >= 1
    response = c.get(f"/api/v1/reports/{kind}/export")
    assert response.status_code == 200 and response.headers["Content-Disposition"].startswith("attachment")
    rows = read_xlsx(response.data)
    assert len(rows) - 1 == data["total"]  # semua baris, bukan hanya satu halaman
    assert db.audit_logs.count_documents({"action": "report_exported", "details.kind": kind}) == 1


def test_stock_products_report_matches_batches(login_as, db):
    rows = login_as(ADMIN).get("/api/v1/reports/stock-products?limit=100").get_json()["data"]
    susu = next(r for r in rows if r["sku"] == "P001")
    expected = sum(b["current_quantity"] for b in db.batches.find({"product_id": db.master_product.find_one({"sku": "P001"})["_id"]}))
    assert susu["available_stock"] == expected and susu["batch_count"] == 2


def test_low_stock_report(login_as, db):
    rows = login_as(SUPERVISOR).get("/api/v1/reports/low-stock").get_json()["data"]
    assert {r["sku"] for r in rows} == {"P005", "P010", "P013"}
    roti = next(r for r in rows if r["sku"] == "P005")
    assert roti["available_stock"] == 9 and roti["min_stock"] == 10 and roti["shortage"] == 1  # 12 - 3 rusak
    assert login_as(STAFF).get("/api/v1/reports/low-stock").status_code == 403


def test_report_filters(login_as):
    c = login_as(SUPERVISOR)
    crit = c.get("/api/v1/reports/near-expiry?status=critical").get_json()
    assert crit["data"] and all(r["expiry_status"] == "critical" for r in crit["data"])
    outs = c.get("/api/v1/reports/movements?movement_type=stock_out").get_json()["data"]
    assert outs and all(r["movement_type"] == "stock_out" for r in outs)
    assert c.get("/api/v1/reports/movements?movement_type=adjustment_in").status_code == 400
    assert c.get("/api/v1/reports/adjustments").get_json()["total"] == 1
    assert c.get("/api/v1/reports/unknown").status_code == 404


def test_export_row_limit_is_enforced(login_as, monkeypatch):
    monkeypatch.setattr(report_services, "MAX_EXPORT_ROWS", 3)
    response = login_as(SUPERVISOR).get("/api/v1/reports/stock-batches/export")
    assert response.status_code == 400 and "lebih sempit" in response.get_json()["error"]["message"]


def test_xlsx_writes_formula_like_text_as_text():
    rows = read_xlsx(build_workbook("Uji", ["A", "B"], [["=1+1", 5], ["\x01ok", None]]))
    assert rows[1] == ["=1+1", 5.0] and rows[2] == ["ok"]


# ---------- riwayat aktivitas ----------

def test_activity_log_is_readable_and_filterable(login_as, db):
    c = login_as(SUPERVISOR)
    data = c.get("/api/v1/activity?action=request_approved").get_json()
    assert data["total"] >= 1 and all(i["action"] == "request_approved" for i in data["data"])
    assert all("actor_name" in i for i in data["data"])
    assert c.get("/api/v1/activity?action=hapus_semua").status_code == 400
    assert c.delete("/api/v1/activity").status_code == 405


def test_audit_never_contains_passwords(login_as, db):
    login_as(ADMIN).post("/api/v1/users", json={"name": "Baru", "email": "b@example.com", "password": "RahasiaSekali1",
                                                "role": "staff"})
    for log in db.audit_logs.find({}):
        assert "RahasiaSekali1" not in str(log)
