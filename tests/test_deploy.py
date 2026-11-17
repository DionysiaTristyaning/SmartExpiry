"""Penyiapan deploy (Vercel): file statis dari public/static, pengaturan khusus Vercel, dan titik masuk index.py."""
import importlib
import os
import sys

import pytest

from app import STATIC_DIR, create_app
from app.config import Config


def test_static_files_are_served_from_public_static(client):
    assert os.path.basename(os.path.dirname(STATIC_DIR)) == "public"
    for path in ("/static/js/common.js", "/static/css/app.css", "/static/vendor/webix/webix.min.js"):
        response = client.get(path)
        assert response.status_code == 200, path
        response.close()


def test_every_script_in_the_page_exists_in_public_static(client):
    import re
    html = client.get("/login").get_data(as_text=True)
    for url in re.findall(r'(?:src|href)="(/static/[^"?]+)', html):
        response = client.get(url)
        assert response.status_code == 200, url
        response.close()


def test_vercel_trusts_proxy_headers_for_https(db, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    app = create_app({"TESTING": True, "SECRET_KEY": "x" * 40, "WTF_CSRF_ENABLED": False}, db=db)
    seen = {}

    @app.get("/skema")
    def scheme():
        from flask import request
        seen["scheme"], seen["host"] = request.scheme, request.host
        return "ok"

    app.test_client().get("/skema", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "contoh.vercel.app"})
    assert seen == {"scheme": "https", "host": "contoh.vercel.app"}


def test_without_vercel_proxy_headers_are_ignored(db, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    app = create_app({"TESTING": True, "SECRET_KEY": "x" * 40, "WTF_CSRF_ENABLED": False}, db=db)
    seen = {}

    @app.get("/skema")
    def scheme():
        from flask import request
        seen["scheme"] = request.scheme
        return "ok"

    app.test_client().get("/skema", headers={"X-Forwarded-Proto": "https"})
    assert seen["scheme"] == "http"  # di komputer sendiri header itu tidak dipercaya


def _secure_cookie_in_fresh_process(**env):
    """Nilai SESSION_COOKIE_SECURE di proses Python baru (supaya tidak mengganggu tes lain)."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    environment = {**os.environ, "SESSION_COOKIE_SECURE": "", "VERCEL": "", **env}  # kosong = tidak diatur
    result = subprocess.run([sys.executable, "-c", "from app.config import Config; print(Config.SESSION_COOKIE_SECURE)"],
                            cwd=root, env=environment, capture_output=True, text=True, timeout=60)
    return result.stdout.strip()


def test_session_cookie_is_secure_by_default_only_on_vercel():
    assert _secure_cookie_in_fresh_process(VERCEL="1") == "True"
    assert _secure_cookie_in_fresh_process() == "False"
    assert _secure_cookie_in_fresh_process(VERCEL="1", SESSION_COOKIE_SECURE="false") == "False"  # tetap bisa dimatikan


def _load_index(monkeypatch, **settings):
    for name, value in settings.items():
        monkeypatch.setattr(Config, name, value)
    sys.modules.pop("index", None)
    return importlib.import_module("index")


def test_index_shows_a_clear_message_when_settings_are_missing(monkeypatch):
    index = _load_index(monkeypatch, SECRET_KEY="", MONGO_URI="")
    try:
        response = index.app.test_client().get("/apa-saja")
        assert response.status_code == 500
        text = response.get_data(as_text=True)
        assert "SECRET_KEY" in text and "MONGO_URI" in text and "Environment Variables" in text
    finally:
        sys.modules.pop("index", None)


def test_index_builds_the_real_app_when_settings_are_present(monkeypatch):
    index = _load_index(monkeypatch, SECRET_KEY="k" * 40, MONGO_URI="mongodb://localhost:27017")
    try:
        assert index.app.test_client().get("/login").status_code == 200
        assert index.app.test_client().get("/api/v1/users").status_code == 401   # aplikasi asli, bukan pesan darurat
    finally:
        sys.modules.pop("index", None)


@pytest.mark.parametrize("name", ["vercel.json", ".python-version", "index.py"])
def test_deploy_files_exist(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(root, name))
