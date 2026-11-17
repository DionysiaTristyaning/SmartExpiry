from flask import Blueprint, current_app, request

from ...common.constants import ROLE_ADMIN, ROLE_SUPERVISOR
from ...common.errors import ValidationFailed
from ...common.http import json_body, ok, page_args, parse_object_id
from ...common.permissions import load_current_user, login_required, roles_required
from . import services

bp = Blueprint("products", __name__)

SORT_FIELDS = {"sku", "name", "category", "price", "created_at"}
MANAGERS = (ROLE_SUPERVISOR, ROLE_ADMIN)  # hak master produk sama untuk Supervisor dan Admin


def bool_arg(value, name="is_active"):
    if value is None or value == "":
        return None
    if value not in ("true", "false"):
        raise ValidationFailed(f"Parameter {name} harus true atau false.")
    return value == "true"


@bp.get("")
@login_required
def list_products():
    skip, limit, sort = page_args(SORT_FIELDS, "sku")
    q = request.args.get("q", "")
    category = request.args.get("category", "")[:50]
    items, total = services.list_products(current_app.db, q, category, bool_arg(request.args.get("is_active")),
                                          skip, limit, sort)
    return ok(items, total=total)


@bp.get("/categories")
@login_required
def categories():
    return ok(services.categories(current_app.db))


@bp.post("")
@roles_required(*MANAGERS)
def create_product():
    return ok(services.create_product(current_app.db, load_current_user(), json_body()), status=201)


@bp.get("/<product_id>")
@login_required
def get_product(product_id):
    return ok(services.get_product(current_app.db, parse_object_id(product_id)))


@bp.put("/<product_id>")
@roles_required(*MANAGERS)
def update_product(product_id):
    return ok(services.update_product(current_app.db, load_current_user(), parse_object_id(product_id), json_body()))


@bp.delete("/<product_id>")
@roles_required(*MANAGERS)
def delete_product(product_id):
    return ok(services.delete_product(current_app.db, load_current_user(), parse_object_id(product_id)))
