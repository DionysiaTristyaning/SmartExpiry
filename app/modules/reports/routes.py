from datetime import datetime

from flask import Blueprint, Response, current_app, request

from ...common.constants import ROLE_ADMIN, ROLE_SUPERVISOR
from ...common.dates import JAKARTA
from ...common.http import ok, page_args
from ...common.permissions import load_current_user, roles_required
from ...common.xlsx import MIME
from . import services

bp = Blueprint("reports", __name__)

VIEWERS = (ROLE_SUPERVISOR, ROLE_ADMIN)  # Staff tidak melihat laporan (SD 4.2)
FILTER_KEYS = ("category", "is_active", "product_id", "status", "has_stock", "movement_type", "fitness",
               "request_type", "date_from", "date_to")


def _args():
    return {key: request.args.get(key, "") for key in FILTER_KEYS}


@bp.get("/<kind>")
@roles_required(*VIEWERS)
def report(kind):
    skip, limit, _ = page_args({"default"}, "default")
    rows, total, summary = services.run(current_app.db, kind, _args(), skip, limit)
    generated = datetime.now(JAKARTA).strftime("%Y-%m-%d %H:%M")
    return ok(rows, total=total, summary=summary, generated_at=generated)


@bp.get("/<kind>/export")
@roles_required(*VIEWERS)
def export(kind):
    content, filename = services.export(current_app.db, load_current_user(), kind, _args())
    return Response(content, mimetype=MIME, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    })
