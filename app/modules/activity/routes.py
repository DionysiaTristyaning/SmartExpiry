from flask import Blueprint, current_app, request

from ...common.constants import ROLE_ADMIN, ROLE_SUPERVISOR
from ...common.dates import parse_date_range
from ...common.http import ok, page_args
from ...common.permissions import roles_required
from . import services

bp = Blueprint("activity", __name__)

VIEWERS = (ROLE_SUPERVISOR, ROLE_ADMIN)


@bp.get("")
@roles_required(*VIEWERS)
def list_activity():
    skip, limit, _ = page_args({"created_at"}, "-created_at")
    filters = {key: request.args.get(key, "") for key in ("actor_id", "action")}
    filters["date_from"], filters["date_to"] = parse_date_range(request.args)
    items, total = services.list_activity(current_app.db, filters, skip, limit)
    return ok(items, total=total)


@bp.get("/options")
@roles_required(*VIEWERS)
def options():
    return ok({"actors": services.actors(current_app.db),
               "actions": [{"id": k, "value": v} for k, v in services.ACTION_LABELS.items()]})
