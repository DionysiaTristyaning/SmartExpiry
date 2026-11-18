from flask import Blueprint, Response, current_app, request

from ...common.constants import ROLE_ADMIN, ROLE_STAFF, ROLE_SUPERVISOR
from ...common.errors import NotFound
from ...common.http import ok
from ...common.permissions import load_current_user, roles_required
from . import services

bp = Blueprint("imports", __name__)

PRODUCT_ROLES = (ROLE_SUPERVISOR, ROLE_ADMIN)
STOCK_ROLES = (ROLE_STAFF,)


@bp.post("/products/preview")
@roles_required(*PRODUCT_ROLES)
def preview_products():
    return ok(services.import_products(current_app.db, load_current_user(), request.files.get("file"), apply=False))


@bp.post("/products/confirm")
@roles_required(*PRODUCT_ROLES)
def confirm_products():
    return ok(services.import_products(current_app.db, load_current_user(), request.files.get("file"), apply=True))


@bp.post("/stock/preview")
@roles_required(*STOCK_ROLES)
def preview_stock():
    return ok(services.import_stock(current_app.db, load_current_user(), request.files.get("file"), apply=False))


@bp.post("/stock/confirm")
@roles_required(*STOCK_ROLES)
def confirm_stock():
    return ok(services.import_stock(current_app.db, load_current_user(), request.files.get("file"), apply=True))


@bp.post("/sales/preview")
@roles_required(*STOCK_ROLES)
def preview_sales():
    return ok(services.import_sales(current_app.db, load_current_user(), request.files.get("file"), apply=False))


@bp.post("/sales/confirm")
@roles_required(*STOCK_ROLES)
def confirm_sales():
    return ok(services.import_sales(current_app.db, load_current_user(), request.files.get("file"), apply=True))


@bp.get("/templates/<kind>")
@roles_required(ROLE_STAFF, ROLE_SUPERVISOR, ROLE_ADMIN)
def template(kind):
    if kind not in ("products", "stock", "sales"):
        raise NotFound("Template tidak ditemukan.")
    # BOM agar Excel membaca UTF-8; baris "sep=;" + pemisah titik koma agar kolom langsung terpisah rapi di Excel
    # berbahasa Indonesia (pemisah bawaannya titik koma). Impor tetap menerima koma maupun titik koma.
    body = "﻿sep=;\n" + services.template_csv(kind).replace(",", ";")
    return Response(body, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="template_{kind}.csv"'})
