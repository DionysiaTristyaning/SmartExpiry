"""Master produk (SD 5.2, 13.2 P1-P2)."""
import pytest

from tests.conftest import ADMIN, STAFF, SUPERVISOR

URL = "/api/v1/products"
BODY = {"sku": "p100", "name": "Teh Hijau 350 ml", "category": "Minuman", "unit": "botol", "price": 5500}


@pytest.mark.parametrize("email", [SUPERVISOR, ADMIN])
def test_supervisor_and_admin_create_product(login_as, db, email):
    response = login_as(email).post(URL, json=BODY)
    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["sku"] == "P100" and data["price"] == 5500 and data["is_active"] is True


def test_duplicate_sku_and_missing_fields(login_as):
    c = login_as(SUPERVISOR)
    assert c.post(URL, json={**BODY, "sku": "P001"}).status_code == 409
    for field in ("name", "category", "unit", "price"):
        body = dict(BODY, sku="P2" + field[:2])
        body.pop(field)
        assert c.post(URL, json=body).status_code == 400, field


@pytest.mark.parametrize("price", [-1, "1.000", "abc", 1.5, True])
def test_price_must_be_whole_rupiah(login_as, price):
    assert login_as(SUPERVISOR).post(URL, json={**BODY, "price": price}).status_code == 400


def test_sku_cannot_change_and_product_can_be_deactivated(login_as, db):
    c = login_as(ADMIN)
    pid = str(db.master_product.find_one({"sku": "P001"})["_id"])
    response = c.put(f"{URL}/{pid}", json={"sku": "ZZZ", "name": "Susu Baru", "category": "Minuman", "unit": "kotak",
                                            "price": 8000, "is_active": False})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["sku"] == "P001" and data["name"] == "Susu Baru" and data["is_active"] is False


def test_product_with_batches_cannot_be_deleted_but_new_one_can(login_as, db):
    c = login_as(SUPERVISOR)
    used = str(db.master_product.find_one({"sku": "P001"})["_id"])
    assert c.delete(f"{URL}/{used}").status_code == 409
    new_id = c.post(URL, json=BODY).get_json()["data"]["id"]
    assert c.delete(f"{URL}/{new_id}").status_code == 200
    assert db.master_product.count_documents({"sku": "P100"}) == 0


def test_list_search_and_filters(login_as):
    c = login_as(STAFF)
    data = c.get(f"{URL}?q=susu").get_json()
    assert data["total"] >= 1 and all("susu" in p["name"].lower() or "susu" in p["sku"].lower() for p in data["data"])
    minuman = c.get(f"{URL}?category=Minuman").get_json()["data"]
    assert minuman and all(p["category"] == "Minuman" for p in minuman)
    assert c.get(f"{URL}?is_active=maybe").status_code == 400


def test_inactive_product_cannot_receive_new_stock(login_as, db):
    from datetime import timedelta

    from app.common.dates import today_jakarta
    from tests.conftest import rid
    db.master_product.update_one({"sku": "P004"}, {"$set": {"is_active": False}})
    today = today_jakarta()
    response = login_as(STAFF).post("/api/v1/batches", json={
        "product_id": str(db.master_product.find_one({"sku": "P004"})["_id"]), "quantity": 5,
        "received_date": today.isoformat(), "expiry_date": (today + timedelta(days=30)).isoformat(),
        "client_request_id": rid()})
    assert response.status_code == 400


@pytest.mark.parametrize("payload", ["<script>alert(1)</script>", "Nama <b>tebal</b>", "=1+1", "-cmd", "@SUM(A1)"])
def test_dangerous_text_is_rejected(login_as, payload):
    assert login_as(SUPERVISOR).post(URL, json={**BODY, "name": payload}).status_code == 400


def test_normal_punctuation_is_allowed(login_as):
    body = {**BODY, "name": "Susu & Roti \"Spesial\" 'A' - 1 kg"}
    assert login_as(SUPERVISOR).post(URL, json=body).status_code == 201


def test_dash_followed_by_space_is_allowed_but_dash_formula_is_not(login_as):
    c = login_as(SUPERVISOR)
    assert c.post(URL, json={**BODY, "sku": "P301", "description": "- kemasan 100 g"}).status_code == 201
    assert c.post(URL, json={**BODY, "sku": "P302", "description": "-2+3"}).status_code == 400


def test_min_stock_is_validated_and_kept_when_not_sent(login_as, db):
    c = login_as(SUPERVISOR)
    pid = str(db.master_product.find_one({"sku": "P001"})["_id"])
    base = {"name": "Susu UHT Cokelat 250 ml", "category": "Minuman", "unit": "kotak", "price": 7000}
    assert c.put(f"/api/v1/products/{pid}", json={**base, "min_stock": -1}).status_code == 400
    assert c.put(f"/api/v1/products/{pid}", json={**base, "min_stock": 30}).status_code == 200
    assert c.put(f"/api/v1/products/{pid}", json=base).status_code == 200
    assert db.master_product.find_one({"sku": "P001"})["min_stock"] == 30


def test_pack_unit_and_size_go_together(login_as):
    c = login_as(SUPERVISOR)
    assert c.post(URL, json={**BODY, "sku": "PK1", "pack_size": 24}).status_code == 400          # nama satuan kosong
    assert c.post(URL, json={**BODY, "sku": "PK2", "pack_unit": "karton"}).status_code == 400     # isi kosong
    assert c.post(URL, json={**BODY, "sku": "PK3", "pack_unit": "karton", "pack_size": 1}).status_code == 400
    ok = c.post(URL, json={**BODY, "sku": "PK4", "pack_unit": "karton", "pack_size": 24})
    assert ok.status_code == 201 and ok.get_json()["data"]["pack_size"] == 24
