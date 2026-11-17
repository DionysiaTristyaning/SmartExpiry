from flask import Blueprint, current_app

from ...common.http import ok
from ...common.permissions import load_current_user, login_required
from . import services

bp = Blueprint("notifications", __name__)


@bp.get("")
@login_required
def list_notifications():
    return ok(services.build(current_app.db, load_current_user()))
