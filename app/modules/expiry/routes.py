from flask import Blueprint, current_app, request

from ...common.http import ok, page_args
from ...common.permissions import login_required
from . import alerts

bp = Blueprint("expiry", __name__)


@bp.get("/alerts")
@login_required
def list_alerts():
    skip, limit, _ = page_args({"expiry_date"}, "expiry_date")
    filters = {key: request.args.get(key, "") for key in ("status", "product_id")}
    items, total = alerts.list_alerts(current_app.db, filters, skip, limit)
    return ok(items, total=total)
