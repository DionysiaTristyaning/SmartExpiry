from pymongo.errors import ConfigurationError, InvalidURI, OperationFailure, ServerSelectionTimeoutError

from app.config import missing_settings, secret_key_warning
from app.db import check_connection
from app.indexes import INDEXES, ensure_indexes


class _Cfg:
    SECRET_KEY = ""
    MONGO_URI = ""


def test_missing_settings_lists_empty_required_values():
    assert missing_settings(_Cfg) == ["SECRET_KEY", "MONGO_URI"]
    _Cfg.SECRET_KEY = "abc"
    assert missing_settings(_Cfg) == ["MONGO_URI"]
    _Cfg.MONGO_URI = "   "
    assert missing_settings(_Cfg) == ["MONGO_URI"]
    _Cfg.MONGO_URI = "mongodb+srv://x"
    assert missing_settings(_Cfg) == []


def test_short_secret_key_gives_a_warning():
    class Cfg:
        SECRET_KEY = "pendek"
        MONGO_URI = "mongodb+srv://x"
    assert "32 karakter" in secret_key_warning(Cfg)
    Cfg.SECRET_KEY = "a" * 64
    assert secret_key_warning(Cfg) is None


class _FakeAdmin:
    def __init__(self, error):
        self.error = error

    def command(self, name):
        if self.error:
            raise self.error
        return {"ok": 1}


class _FakeDb:
    def __init__(self, error=None):
        self.client = type("C", (), {"admin": _FakeAdmin(error)})()


def test_connection_errors_get_friendly_messages_without_secrets():
    assert check_connection(_FakeDb()) is None
    assert "MONGO_URI" in check_connection(_FakeDb(InvalidURI("x")))
    assert "MONGO_URI" in check_connection(_FakeDb(ConfigurationError("x")))
    assert "password" in check_connection(_FakeDb(OperationFailure("bad auth", code=18))).lower()
    assert "Network Access" in check_connection(_FakeDb(ServerSelectionTimeoutError("x")))
    assert "pass@host" not in check_connection(_FakeDb(RuntimeError("mongodb+srv://user:pass@host")))


def test_indexes_are_idempotent_and_unique_keys_exist(db):
    first = ensure_indexes(db, skip_text=True)
    assert ensure_indexes(db, skip_text=True) == first
    assert len(first) == len(INDEXES) - 1  # indeks teks dilewati di database tiruan
    uniques = {(c, tuple(k for k, _ in keys)) for c, keys, opt in INDEXES if opt.get("unique")}
    for expected in [("master_karyawan", ("email",)), ("master_product", ("sku",)), ("batches", ("batch_number",)),
                     ("handling_requests", ("request_number",)), ("stock_movements", ("client_request_id",)),
                     ("stock_movements", ("source.handling_request_id",)), ("stock_movements", ("source.inspection_id",))]:
        assert expected in uniques


def test_no_outlet_or_settings_collection_is_used():
    collections = {c for c, _, _ in INDEXES}
    assert collections == {"master_karyawan", "master_product", "batches", "stock_movements", "inspections", "handling_requests",
                           "audit_logs"}


def test_database_conflicts_and_outages_get_clear_messages(app, login_as):
    from unittest import mock

    from pymongo.errors import OperationFailure, ServerSelectionTimeoutError

    c = login_as("rudistaff@gmail.com")
    conflict = OperationFailure("WriteConflict", code=112)
    with mock.patch("app.modules.dashboard.services.summary", side_effect=conflict):
        response = c.get("/api/v1/dashboard/summary")
    assert response.status_code == 409 and "coba lagi" in response.get_json()["error"]["message"]
    with mock.patch("app.modules.dashboard.services.summary", side_effect=ServerSelectionTimeoutError("x")):
        response = c.get("/api/v1/dashboard/summary")
    assert response.status_code == 503 and "internet" in response.get_json()["error"]["message"]
