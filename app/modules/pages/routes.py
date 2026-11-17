"""Halaman HTML: login dan kerangka aplikasi."""
from flask import Blueprint, redirect, render_template, url_for

from ...common.permissions import load_current_user, page_login_required

bp = Blueprint("pages", __name__, template_folder="../../templates")


@bp.get("/")
def index():
    if load_current_user():
        return redirect(url_for("pages.app_page"))
    return redirect(url_for("pages.login_page"))


@bp.get("/login")
def login_page():
    if load_current_user():
        return redirect(url_for("pages.app_page"))
    return render_template("login.html")


@bp.get("/app")
@page_login_required
def app_page():
    return render_template("app.html")
