from flask import Blueprint, current_app, request

from ...common.constants import ROLE_STAFF, ROLE_SUPERVISOR
from ...common.dates import parse_date_range
from ...common.http import json_body, ok, page_args, parse_object_id
from ...common.permissions import load_current_user, login_required, roles_required
from ..movements import services as movement_services
from . import services

bp = Blueprint("inspections", __name__)

SORT_FIELDS = {"inspected_at", "difference"}


@bp.get("")
@login_required
def list_inspections():
    skip, limit, sort = page_args(SORT_FIELDS, "-inspected_at")
    filters = {key: request.args.get(key, "") for key in ("batch_id", "product_id", "fitness", "has_difference", "correction")}
    filters["date_from"], filters["date_to"] = parse_date_range(request.args)
    items, total = services.list_inspections(current_app.db, filters, skip, limit, sort)
    return ok(items, total=total)


@bp.post("")
@roles_required(ROLE_STAFF, ROLE_SUPERVISOR)
def create_inspection():
    return ok(services.create_inspection(current_app.db, load_current_user(), json_body()), status=201)


@bp.get("/<inspection_id>")
@login_required
def get_inspection(inspection_id):
    return ok(services.get_inspection(current_app.db, parse_object_id(inspection_id)))


@bp.post("/<inspection_id>/adjust")
@roles_required(ROLE_STAFF)
def adjust(inspection_id):
    db = current_app.db
    movement = services.adjust_from_inspection(db, load_current_user(), parse_object_id(inspection_id))
    return ok(movement_services.enrich(db, [movement])[0], status=201)


@bp.post("/<inspection_id>/expiry-correction/approve")
@roles_required(ROLE_SUPERVISOR)
def approve_correction(inspection_id):
    return ok(services.decide_expiry_correction(current_app.db, load_current_user(), parse_object_id(inspection_id),
                                                "approve", json_body()))


@bp.post("/<inspection_id>/expiry-correction/reject")
@roles_required(ROLE_SUPERVISOR)
def reject_correction(inspection_id):
    return ok(services.decide_expiry_correction(current_app.db, load_current_user(), parse_object_id(inspection_id),
                                                "reject", json_body()))
