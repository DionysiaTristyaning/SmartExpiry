"""Pabrik aplikasi Flask."""
import os

from flask import Flask, request
from flask_wtf.csrf import CSRFError, CSRFProtect
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError

from .common.errors import AppError
from .common.http import fail
from .config import Config
from .db import create_database

csrf = CSRFProtect()


# File statis (CSS, JS, Webix) ada di public/static: Vercel hanya melayani file statis dari folder public/,
# jadi lokasinya dipakai sama untuk komputer sendiri maupun Vercel (satu salinan saja).
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "static")


def create_app(config_overrides=None, db=None):
    """Buat aplikasi. `db` diisi hanya saat pengujian (database tiruan)."""
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    if os.getenv("VERCEL"):
        # Di Vercel aplikasi berada di belakang proxy HTTPS: percayai satu lapis header X-Forwarded-*
        # supaya alamat, skema (https), dan cookie aman terbaca benar.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.db = db if db is not None else create_database(app.config["MONGO_URI"], app.config["DATABASE_NAME"])

    csrf.init_app(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    _register_asset_version(app)
    return app


def _register_asset_version(app):
    """Nomor versi file statis (waktu ubah terbaru) ditambahkan ke URL CSS/JS agar cache lama tidak terpakai."""
    static_dir = app.static_folder or ""

    def newest_mtime():
        newest = 0
        for folder, _, files in os.walk(os.path.join(static_dir, "js")):
            for name in files:
                newest = max(newest, int(os.path.getmtime(os.path.join(folder, name))))
        css = os.path.join(static_dir, "css", "app.css")
        return max(newest, int(os.path.getmtime(css))) if os.path.exists(css) else newest

    version = newest_mtime()

    @app.context_processor
    def inject_asset_version():
        return {"asset_v": version}


def _register_blueprints(app):
    from .modules.activity.routes import bp as activity_bp
    from .modules.auth.routes import bp as auth_bp
    from .modules.batches.routes import bp as batches_bp
    from .modules.dashboard.routes import bp as dashboard_bp
    from .modules.expiry.routes import bp as expiry_bp
    from .modules.imports.routes import bp as imports_bp
    from .modules.inspections.routes import bp as inspections_bp
    from .modules.movements.routes import bp as movements_bp
    from .modules.notifications.routes import bp as notifications_bp
    from .modules.pages.routes import bp as pages_bp
    from .modules.products.routes import bp as products_bp
    from .modules.recommendations.routes import bp as recommendations_bp
    from .modules.reports.routes import bp as reports_bp
    from .modules.requests.routes import bp as requests_bp
    from .modules.users.routes import bp as users_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(users_bp, url_prefix="/api/v1/users")
    app.register_blueprint(products_bp, url_prefix="/api/v1/products")
    app.register_blueprint(batches_bp, url_prefix="/api/v1/batches")
    app.register_blueprint(movements_bp, url_prefix="/api/v1/movements")
    app.register_blueprint(imports_bp, url_prefix="/api/v1/imports")
    app.register_blueprint(expiry_bp, url_prefix="/api/v1/expiry")
    app.register_blueprint(inspections_bp, url_prefix="/api/v1/inspections")
    app.register_blueprint(recommendations_bp, url_prefix="/api/v1/recommendations")
    app.register_blueprint(requests_bp, url_prefix="/api/v1/requests")
    app.register_blueprint(dashboard_bp, url_prefix="/api/v1/dashboard")
    app.register_blueprint(notifications_bp, url_prefix="/api/v1/notifications")
    app.register_blueprint(reports_bp, url_prefix="/api/v1/reports")
    app.register_blueprint(activity_bp, url_prefix="/api/v1/activity")


def _register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(exc):
        return fail(exc.message, exc.status, exc.fields)

    @app.errorhandler(PyMongoError)
    def handle_database_error(exc):
        """Kesalahan database diterjemahkan menjadi pesan yang jelas (tanpa detail internal)."""
        labels = getattr(exc, "has_error_label", None)
        busy = (labels and (exc.has_error_label("TransientTransactionError")
                            or exc.has_error_label("UnknownTransactionCommitResult"))) \
            or (isinstance(exc, OperationFailure) and exc.code == 112)  # 112 = WriteConflict
        if busy:
            # Dua pengguna mengubah data yang sama pada saat bersamaan; transaksi sudah dibatalkan utuh.
            return fail("Data yang sama sedang diubah pengguna lain. Tidak ada yang tersimpan; silakan coba lagi.", 409)
        if isinstance(exc, ConnectionFailure):
            return fail("Data tidak bisa diambil karena koneksi terputus. Periksa koneksi internet lalu coba lagi.", 503)
        app.logger.exception("Kesalahan database")
        return fail("Ada masalah saat mengambil atau menyimpan data. Coba lagi.", 500)

    @app.errorhandler(CSRFError)
    def handle_csrf(exc):
        return fail("Halaman ini sudah terlalu lama terbuka. Muat ulang halaman (tekan F5) lalu coba lagi.", 400)

    @app.errorhandler(404)
    def handle_404(exc):
        if request.path.startswith("/api/"):
            return fail("Data tidak ditemukan.", 404)
        return "Halaman tidak ditemukan.", 404

    @app.errorhandler(405)
    def handle_405(exc):
        return fail("Permintaan tidak dikenali.", 405)

    @app.errorhandler(413)
    def handle_413(exc):
        return fail("File atau data terlalu besar.", 413)

    @app.errorhandler(500)
    def handle_500(exc):
        # Detail error sengaja tidak dikirim ke pengguna.
        if request.path.startswith("/api/"):
            return fail("Ada masalah di aplikasi. Coba lagi beberapa saat lagi.", 500)
        return "Ada masalah di aplikasi. Coba lagi beberapa saat lagi.", 500


def _register_security_headers(app):
    @app.after_request
    def add_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.path.startswith("/api/") or request.path in ("/login", "/app"):
            response.headers["Cache-Control"] = "no-store"
        elif request.path.startswith("/static/"):
            # File CSS/JS selalu dicek ulang ke server (hemat lewat 304), supaya browser tidak memakai JS lama
            # yang tidak cocok dengan JS baru.
            response.headers["Cache-Control"] = "no-cache"
        return response
