from flask import Blueprint, current_app, request

from ...common.constants import ROLE_STAFF
from ...common.http import json_body, ok, page_args, parse_object_id
from ...common.permissions import load_current_user, login_required, roles_required
from . import services

bp = Blueprint("batches", __name__)

SORT_FIELDS = {"expiry_date", "received_date", "batch_number", "created_at", "current_quantity"}


@bp.get("")
@login_required
def list_batches():
    skip, limit, sort = page_args(SORT_FIELDS, "expiry_date")
    filters = {key: request.args.get(key, "") for key in ("product_id", "status", "q", "has_stock")}
    items, total = services.list_batches(current_app.db, filters, skip, limit, sort)
    return ok(items, total=total)


@bp.get("/fefo")
@login_required
def fefo():
    """Saran FEFO untuk stok keluar: batch layak jual milik satu produk, kedaluwarsa terdekat lebih dulu."""
    return ok(services.fefo_batches(current_app.db, parse_object_id(request.args.get("product_id"), "product_id")))


@bp.post("/preview")
@roles_required(ROLE_STAFF)
def preview():
    """Layar konfirmasi stok masuk: validasi + status kedaluwarsa, tanpa menyimpan."""
    return ok(services.preview_stock_in(current_app.db, json_body()))


@bp.post("")
@roles_required(ROLE_STAFF)
def create_stock_in():
    """Bila semua barang ditolak, tidak ada batch: respons berisi rejected_all = true."""
    return ok(services.create_stock_in(current_app.db, load_current_user(), json_body()), status=201)


@bp.get("/<batch_id>")
@login_required
def get_batch(batch_id):
    return ok(services.get_batch_detail(current_app.db, parse_object_id(batch_id)))
