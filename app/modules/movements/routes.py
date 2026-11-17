from flask import Blueprint, current_app, request

from ...common.constants import ROLE_STAFF
from ...common.dates import parse_date_range
from ...common.http import json_body, ok, page_args, parse_object_id
from ...common.permissions import load_current_user, login_required, roles_required
from . import services

bp = Blueprint("movements", __name__)

SORT_FIELDS = {"created_at", "movement_date", "quantity"}


@bp.get("")
@login_required
def list_movements():
    skip, limit, sort = page_args(SORT_FIELDS, "-created_at")
    filters = {key: request.args.get(key, "") for key in ("batch_id", "product_id", "movement_type")}
    filters["date_from"], filters["date_to"] = parse_date_range(request.args)
    items, total = services.list_movements(current_app.db, filters, skip, limit, sort)
    return ok(items, total=total)


@bp.post("/stock-out")
@roles_required(ROLE_STAFF)
def stock_out():
    """Dengan product_id: rekap penjualan per produk (otomatis FEFO). Dengan batch_id: satu batch tertentu."""
    body = json_body()
    if body.get("product_id") and not body.get("batch_id"):
        return ok(services.record_sale(current_app.db, load_current_user(), body), status=201)
    return ok(services.record_stock_out(current_app.db, load_current_user(), body), status=201)


@bp.get("/<movement_id>")
@login_required
def get_movement(movement_id):
    return ok(services.get_movement(current_app.db, parse_object_id(movement_id)))
