from flask import Blueprint, current_app, request

from ...common.constants import ROLE_ADMIN
from ...common.http import json_body, ok, page_args, parse_object_id
from ...common.permissions import load_current_user, roles_required
from . import services

bp = Blueprint("users", __name__)

SORT_FIELDS = {"name", "email", "role", "created_at"}


@bp.get("")
@roles_required(ROLE_ADMIN)
def list_users():
    skip, limit, sort = page_args(SORT_FIELDS, "name")
    filters = {key: request.args.get(key, "") for key in ("role", "is_active")}
    items, total = services.list_users(current_app.db, filters, skip, limit, sort)
    return ok(items, total=total)


@bp.post("")
@roles_required(ROLE_ADMIN)
def create_user():
    return ok(services.create_user(current_app.db, load_current_user(), json_body()), status=201)


@bp.get("/<user_id>")
@roles_required(ROLE_ADMIN)
def get_user(user_id):
    return ok(services.get_user(current_app.db, parse_object_id(user_id)))


@bp.put("/<user_id>")
@roles_required(ROLE_ADMIN)
def update_user(user_id):
    return ok(services.update_user(current_app.db, load_current_user(), parse_object_id(user_id), json_body()))


@bp.post("/<user_id>/deactivate")
@roles_required(ROLE_ADMIN)
def deactivate(user_id):
    return ok(services.set_active(current_app.db, load_current_user(), parse_object_id(user_id), False))


@bp.post("/<user_id>/activate")
@roles_required(ROLE_ADMIN)
def activate(user_id):
    return ok(services.set_active(current_app.db, load_current_user(), parse_object_id(user_id), True))


@bp.post("/<user_id>/reset-password")
@roles_required(ROLE_ADMIN)
def reset_password(user_id):
    return ok(services.reset_password(current_app.db, load_current_user(), parse_object_id(user_id), json_body()))
