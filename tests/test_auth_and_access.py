"""SD 13.1: autentikasi dan otorisasi (matriks hak akses SD 4.2)."""
import pytest

from tests.conftest import ADMIN, STAFF, SUPERVISOR, batch_of, login, rid


def test_login_success_and_me(client):
    response = login(client, STAFF)
    assert response.status_code == 200
    me = client.get("/api/v1/auth/me").get_json()["data"]
    assert me["email"] == STAFF and me["role"] == "staff" and "password_hash" not in me


def test_wrong_password_and_unknown_email_give_the_same_generic_message(client, db):
    bad = login(client, STAFF, "salah-sekali")
    unknown = login(client, "tidakada@example.com", "salah-sekali")
    assert bad.status_code == unknown.status_code == 401
    assert bad.get_json()["error"]["message"] == unknown.get_json()["error"]["message"]
    assert db.audit_logs.count_documents({"action": "login_failed"}) == 2


def test_inactive_account_cannot_login(client):
    assert login(client, "tonostaff@gmail.com").status_code == 401


def test_deactivation_takes_effect_on_the_next_request(login_as, db):
    c = login_as(STAFF)
    assert c.get("/api/v1/auth/me").status_code == 200
    db.master_karyawan.update_one({"email": STAFF}, {"$set": {"is_active": False}})
    assert c.get("/api/v1/auth/me").status_code == 401


def test_logout_clears_session(login_as):
    c = login_as(STAFF)
    assert c.post("/api/v1/auth/logout").status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 401


def test_all_api_requires_login(client):
    for url in ("/api/v1/batches", "/api/v1/products", "/api/v1/requests", "/api/v1/dashboard/summary",
                "/api/v1/reports/stock-products", "/api/v1/activity", "/api/v1/users", "/api/v1/notifications"):
        assert client.get(url).status_code == 401, url


def test_csrf_is_required_for_changes(db):
    from app import create_app
    app = create_app({"TESTING": True, "SECRET_KEY": "k" * 40}, db=db)  # CSRF aktif
    c = app.test_client()
    assert c.post("/api/v1/auth/login", json={"email": STAFF, "password": "x"}).status_code == 400


# ---------- matriks hak akses ----------

def _stock_in_body(db):
    from datetime import timedelta

    from app.common.dates import today_jakarta
    today = today_jakarta()
    return {"product_id": str(db.master_product.find_one({"sku": "P004"})["_id"]), "quantity": 5,
            "received_date": today.isoformat(), "expiry_date": (today + timedelta(days=40)).isoformat(),
            "client_request_id": rid()}


@pytest.mark.parametrize("email", [SUPERVISOR, ADMIN])
def test_only_staff_records_stock_and_submits_requests(login_as, db, email):
    c = login_as(email)
    batch = batch_of(db, "P004")
    assert c.post("/api/v1/batches", json=_stock_in_body(db)).status_code == 403
    assert c.post("/api/v1/movements/stock-out",
                  json={"batch_id": str(batch["_id"]), "quantity": 1, "client_request_id": rid()}).status_code == 403
    assert c.post("/api/v1/requests", json={"batch_id": str(batch["_id"]), "request_type": "return", "quantity": 1,
                                            "reason": "x", "client_request_id": rid()}).status_code == 403
    inspection = db.inspections.find_one({"difference": {"$ne": 0}})
    assert c.post(f"/api/v1/inspections/{inspection['_id']}/adjust", json={}).status_code == 403


def test_staff_cannot_manage_products_users_reports_or_approve(login_as, db):
    c = login_as(STAFF)
    assert c.post("/api/v1/products", json={"sku": "X1", "name": "a", "category": "b", "unit": "pcs",
                                            "price": 1}).status_code == 403
    assert c.get("/api/v1/users").status_code == 403
    assert c.get("/api/v1/reports/stock-products").status_code == 403
    assert c.get("/api/v1/activity").status_code == 403
    pending = db.handling_requests.find_one({"status": "pending"})
    assert c.post(f"/api/v1/requests/{pending['_id']}/approve", json={}).status_code == 403


def test_admin_cannot_approve_or_inspect(login_as, db):
    c = login_as(ADMIN)
    pending = db.handling_requests.find_one({"status": "pending"})
    assert c.post(f"/api/v1/requests/{pending['_id']}/approve", json={}).status_code == 403
    batch = batch_of(db, "P004")
    assert c.post("/api/v1/inspections", json={"batch_id": str(batch["_id"]), "physical_quantity": 1,
                                               "product_condition": "baik", "packaging_condition": "baik"}).status_code == 403


def test_supervisor_cannot_manage_users(login_as):
    assert login_as(SUPERVISOR).get("/api/v1/users").status_code == 403


@pytest.mark.parametrize("email", [STAFF, SUPERVISOR, ADMIN])
def test_everyone_can_view_operational_data(login_as, email):
    c = login_as(email)
    for url in ("/api/v1/dashboard/summary", "/api/v1/products", "/api/v1/batches", "/api/v1/movements",
                "/api/v1/expiry/alerts", "/api/v1/inspections", "/api/v1/recommendations", "/api/v1/requests"):
        assert c.get(url).status_code == 200, (email, url)


def test_invalid_object_id_is_a_clean_400(login_as):
    assert login_as(STAFF).get("/api/v1/batches/bukan-id").status_code == 400


def test_mongodb_operator_in_query_is_not_executed(login_as):
    c = login_as(STAFF)
    assert c.get("/api/v1/batches?status[$ne]=x").status_code == 200  # parameter tak dikenal diabaikan
    assert c.get("/api/v1/batches?status=$ne").status_code == 400
    assert c.get("/api/v1/batches?sort=password_hash").status_code == 400


def test_login_email_is_case_insensitive(client):
    assert login(client, "Budiadmin@gmail.com", "Budiadmin").status_code == 200
    assert login(client, "budiadmin@gmail.com", "budiadmin").status_code == 401  # password tetap peka huruf besar/kecil


def test_account_is_locked_after_five_wrong_passwords(client, db):
    email = "rinastaff@gmail.com"
    for _ in range(4):
        response = login(client, email, "salah-password")
        assert response.status_code == 401 and response.get_json()["error"]["message"] == "Email atau password salah."
    fifth = login(client, email, "salah-password")
    assert fifth.status_code == 401 and "dikunci 15 menit" in fifth.get_json()["error"]["message"]
    # password benar pun ditolak selama terkunci
    locked = login(client, email)
    assert locked.status_code == 401 and "Coba lagi dalam" in locked.get_json()["error"]["message"]
    assert db.audit_logs.find_one({"action": "login_locked"})


def test_success_resets_failed_count_and_admin_reset_unlocks(login_as, client, db):
    email = "dewistaff@gmail.com"
    for _ in range(3):
        login(client, email, "salah")
    assert login(client, email).status_code == 200
    assert db.master_karyawan.find_one({"email": email})["failed_logins"] == 0
    for _ in range(5):
        login(client, email, "salah")
    user = db.master_karyawan.find_one({"email": email})
    admin = login_as("budiadmin@gmail.com")
    listed = admin.get(f"/api/v1/users/{user['_id']}").get_json()["data"]
    assert listed["locked_minutes"] > 0
    assert admin.post(f"/api/v1/users/{user['_id']}/reset-password",
                      json={"new_password": "PasswordBaru1"}).status_code == 200
    assert login(client, email, "PasswordBaru1").status_code == 200


def test_copied_session_cookie_is_useless_after_logout(login_as, app):
    c = login_as(STAFF)
    stolen = c.get_cookie("session").value
    assert c.post("/api/v1/auth/logout").status_code == 200
    thief = app.test_client()
    thief.set_cookie("session", stolen)
    assert thief.get("/api/v1/auth/me").status_code == 401


def test_pages_and_api_need_login_and_password_is_hashed(client, db):
    assert client.get("/app").status_code == 302 and "/login" in client.get("/app").headers["Location"]
    for url in ("/api/v1/products", "/api/v1/batches", "/api/v1/users", "/api/v1/reports/stock-products",
                "/api/v1/activity", "/api/v1/dashboard/summary"):
        assert client.get(url).status_code == 401, url
    user = db.master_karyawan.find_one({"email": STAFF})
    assert user["password_hash"].startswith(("scrypt:", "pbkdf2:")) and "Rudistaff" not in str(user)



# ---------- sesi berakhir bila tidak ada aktivitas ----------

def test_session_ends_after_idle_time(login_as):
    import time

    from app.common.constants import IDLE_TIMEOUT_MINUTES
    c = login_as(STAFF)
    with c.session_transaction() as sess:
        sess["seen"] = int(time.time()) - IDLE_TIMEOUT_MINUTES * 60 - 5
    response = c.get("/api/v1/auth/me")
    assert response.status_code == 401 and "tidak ada aktivitas" in response.get_json()["error"]["message"]
    assert c.get("/app").headers["Location"].endswith("/login")  # sesi sudah dihapus


def test_background_polling_does_not_count_as_activity(login_as):
    import time
    c = login_as(STAFF)
    old = int(time.time()) - 600
    with c.session_transaction() as sess:
        sess["seen"] = old
    assert c.get("/api/v1/notifications", headers={"X-Background": "1"}).status_code == 200
    with c.session_transaction() as sess:
        assert sess["seen"] == old                       # lonceng otomatis tidak memperpanjang sesi
    c.get("/api/v1/auth/me")
    with c.session_transaction() as sess:
        assert sess["seen"] > old                        # aktivitas pengguna memperpanjang sesi
