from flask import Blueprint, current_app

from ...common.http import ok
from ...common.permissions import load_current_user, login_required
from . import services

bp = Blueprint("dashboard", __name__)


@bp.get("/summary")
@login_required
def summary():
    return ok(services.summary(current_app.db, load_current_user()))
