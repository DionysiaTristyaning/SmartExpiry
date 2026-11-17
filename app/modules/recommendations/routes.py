from flask import Blueprint, current_app, request

from ...common.http import ok, page_args, parse_object_id
from ...common.permissions import login_required
from . import services

bp = Blueprint("recommendations", __name__)


@bp.get("")
@login_required
def list_recommendations():
    skip, limit, _ = page_args({"priority"}, "priority")
    filters = {key: request.args.get(key, "") for key in ("action", "product_id")}
    items, total = services.list_recommendations(current_app.db, filters, skip, limit)
    return ok(items, total=total)


@bp.get("/<batch_id>")
@login_required
def get_recommendation(batch_id):
    return ok(services.get_recommendation(current_app.db, parse_object_id(batch_id)))
