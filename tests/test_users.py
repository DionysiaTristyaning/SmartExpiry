"""Manajemen akun oleh Admin (SD 4.1, FR-USR)."""
from tests.conftest import ADMIN, STAFF, login

URL = "/api/v1/users"


def _uid(db, email):
    return str(db.master_karyawan.find_one({"email": email})["_id"])


def test_admin_creates_user_and_new_user_can_login(login_as, client, db):
    body = {"name": "Staff Baru", "email": "baru@example.com", "password": "Rahasia123", "role": "staff"}
    response = login_as(ADMIN).post(URL, json=body)
    assert response.status_code == 201 and "password_hash" not in response.get_json()["data"]
    assert db.master_karyawan.find_one({"email": "baru@example.com"})["password_hash"] != "Rahasia123"  # disimpan sebagai hash
    assert login(client, "baru@example.com", "Rahasia123").status_code == 200


def test_duplicate_email_short_password_and_bad_role_are_rejected(login_as):
    c = login_as(ADMIN)
    assert c.post(URL, json={"name": "A", "email": STAFF, "password": "Rahasia123", "role": "staff"}).status_code in (400, 409)
    assert c.post(URL, json={"name": "Abc", "email": "x1@example.com", "password": "pendek", "role": "staff"}).status_code == 400
    assert c.post(URL, json={"name": "Abc", "email": "x2@example.com", "password": "Rahasia123", "role": "manager"}).status_code == 400


def test_update_role_and_name(login_as, db):
    c = login_as(ADMIN)
    response = c.put(f"{URL}/{_uid(db, STAFF)}", json={"name": "Andi Baru", "role": "supervisor"})
    assert response.status_code == 200
    user = db.master_karyawan.find_one({"email": STAFF})
    assert user["role"] == "supervisor" and user["name"] == "Andi Baru"


def test_admin_cannot_deactivate_or_demote_self(login_as, db):
    c = login_as(ADMIN)
    assert c.post(f"{URL}/{_uid(db, ADMIN)}/deactivate").status_code == 400
    assert c.put(f"{URL}/{_uid(db, ADMIN)}", json={"name": "Admin", "role": "staff"}).status_code == 400


def test_last_active_admin_is_protected(login_as, db):
    import pytest
    from bson import ObjectId

    from app.common.errors import ValidationFailed
    from app.modules.users import services

    c = login_as(ADMIN)
    c.post(URL, json={"name": "Admin Dua", "email": "admin2@example.com", "password": "Rahasia123", "role": "admin"})
    admin2 = login_as(ADMIN).application.test_client()
    assert login(admin2, "admin2@example.com", "Rahasia123").status_code == 200
    assert admin2.post("/api/v1/auth/change-password",
                       json={"old_password": "Rahasia123", "new_password": "Rahasia456"}).status_code == 200
    assert admin2.post(f"{URL}/{_uid(db, ADMIN)}/deactivate").status_code == 200
    # admin2 kini Admin aktif terakhir: tidak boleh dinonaktifkan atau diturunkan perannya oleh siapa pun
    other = {"_id": ObjectId(), "role": "admin"}
    last = db.master_karyawan.find_one({"email": "admin2@example.com"})["_id"]
    with pytest.raises(ValidationFailed):
        services.set_active(db, other, last, False)
    with pytest.raises(ValidationFailed):
        services.update_user(db, other, last, {"name": "Admin Dua", "role": "staff"})


def test_deactivate_activate_and_reset_password(login_as, client, db):
    c = login_as(ADMIN)
    uid = _uid(db, STAFF)
    assert c.post(f"{URL}/{uid}/deactivate").status_code == 200
    assert login(client, STAFF).status_code == 401
    assert c.post(f"{URL}/{uid}/activate").status_code == 200
    assert c.post(f"{URL}/{uid}/reset-password", json={"new_password": "PasswordBaru1"}).status_code == 200
    assert login(client, STAFF).status_code == 401
    assert login(client, STAFF, "PasswordBaru1").status_code == 200
    assert db.audit_logs.count_documents({"action": "user_password_reset"}) == 1


def test_users_are_never_deleted(login_as, db):
    assert login_as(ADMIN).delete(f"{URL}/{_uid(db, STAFF)}").status_code == 405


def test_password_reset_ends_existing_sessions(login_as, db):
    staff = login_as(STAFF)
    assert staff.get("/api/v1/auth/me").status_code == 200
    login_as(ADMIN).post(f"{URL}/{_uid(db, STAFF)}/reset-password", json={"new_password": "PasswordBaru1"})
    assert staff.get("/api/v1/auth/me").status_code == 401          # sesi lama berakhir
    fresh = login_as(ADMIN).application.test_client()
    assert login(fresh, STAFF, "PasswordBaru1").status_code == 200  # login baru dengan password baru berhasil
    assert fresh.get("/api/v1/auth/me").status_code == 200



# ---------- ganti password sendiri ----------

def test_new_user_must_change_password_before_using_the_app(login_as, client, db):
    login_as(ADMIN).post(URL, json={"name": "Baru", "email": "baru2@example.com", "password": "Sementara1",
                                    "role": "staff"})
    assert login(client, "baru2@example.com", "Sementara1").get_json()["data"]["must_change_password"] is True
    assert client.get("/api/v1/products").status_code == 403                   # belum boleh memakai aplikasi
    assert client.get("/api/v1/auth/me").status_code == 200                    # profil tetap bisa dibaca
    bad = client.post("/api/v1/auth/change-password", json={"old_password": "salah", "new_password": "PunyaSaya9"})
    assert bad.status_code == 400
    same = client.post("/api/v1/auth/change-password", json={"old_password": "Sementara1", "new_password": "Sementara1"})
    assert same.status_code == 400
    short = client.post("/api/v1/auth/change-password", json={"old_password": "Sementara1", "new_password": "pendek"})
    assert short.status_code == 400
    done = client.post("/api/v1/auth/change-password", json={"old_password": "Sementara1", "new_password": "PunyaSaya9"})
    assert done.status_code == 200 and done.get_json()["data"]["must_change_password"] is False
    assert client.get("/api/v1/products").status_code == 200                   # sesi ini tetap berlaku
    assert db.audit_logs.find_one({"action": "password_changed"})


def test_admin_reset_forces_change_and_admin_no_longer_knows_password(login_as, client, db):
    login_as(ADMIN).post(f"{URL}/{_uid(db, STAFF)}/reset-password", json={"new_password": "DariAdmin1"})
    login(client, STAFF, "DariAdmin1")
    assert client.get("/api/v1/batches").status_code == 403
    client.post("/api/v1/auth/change-password", json={"old_password": "DariAdmin1", "new_password": "RahasiaRudi9"})
    assert login(login_as(ADMIN).application.test_client(), STAFF, "DariAdmin1").status_code == 401


def test_changing_password_ends_other_sessions(login_as, app):
    a, b = login_as(STAFF), login_as(STAFF)
    assert a.post("/api/v1/auth/change-password",
                  json={"old_password": "Rudistaff", "new_password": "BaruSekali9"}).status_code == 200
    assert a.get("/api/v1/auth/me").status_code == 200
    assert b.get("/api/v1/auth/me").status_code == 401
