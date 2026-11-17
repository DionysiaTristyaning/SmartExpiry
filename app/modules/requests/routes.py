from flask import Blueprint, current_app, request

from ...common.constants import ROLE_STAFF, ROLE_SUPERVISOR
from ...common.dates import parse_date_range
from ...common.http import json_body, ok, page_args, parse_object_id
from ...common.permissions import load_current_user, login_required, roles_required
from . import services

bp = Blueprint("requests", __name__)

SORT_FIELDS = {"submitted_at", "reviewed_at", "completed_at"}


@bp.get("")
@login_required
def list_requests():
    skip, limit, sort = page_args(SORT_FIELDS, "-submitted_at")
    filters = {key: request.args.get(key, "") for key in ("status", "request_type", "batch_id")}
    filters["date_from"], filters["date_to"] = parse_date_range(request.args)
    items, total = services.list_requests(current_app.db, filters, skip, limit, sort)
    return ok(items, total=total)


@bp.post("")
@roles_required(ROLE_STAFF)
def submit():
    doc = services.submit(current_app.db, load_current_user(), json_body())
    return ok(services.get_request(current_app.db, doc["_id"]), status=201)


@bp.get("/<request_id>")
@login_required
def get_request(request_id):
    return ok(services.get_request(current_app.db, parse_object_id(request_id)))


@bp.post("/<request_id>/approve")
@roles_required(ROLE_SUPERVISOR)
def approve(request_id):
    oid = parse_object_id(request_id)
    services.review(current_app.db, load_current_user(), oid, "approve", json_body())
    return ok(services.get_request(current_app.db, oid))


@bp.post("/<request_id>/reject")
@roles_required(ROLE_SUPERVISOR)
def reject(request_id):
    oid = parse_object_id(request_id)
    services.review(current_app.db, load_current_user(), oid, "reject", json_body())
    return ok(services.get_request(current_app.db, oid))


@bp.post("/<request_id>/cancel")
@roles_required(ROLE_STAFF, ROLE_SUPERVISOR)
def cancel(request_id):
    oid = parse_object_id(request_id)
    services.cancel(current_app.db, load_current_user(), oid, json_body())
    return ok(services.get_request(current_app.db, oid))


@bp.post("/<request_id>/complete")
@roles_required(ROLE_STAFF)
def complete(request_id):
    oid = parse_object_id(request_id)
    services.complete(current_app.db, load_current_user(), oid, json_body())
    return ok(services.get_request(current_app.db, oid))
