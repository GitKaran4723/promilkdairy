# auth.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Customer

auth = Blueprint("auth", __name__, url_prefix="/auth")

@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(phone=phone).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid phone or password", "error")
            return redirect(url_for("auth.login"))
        login_user(user, remember=bool(request.form.get("remember")))
        # redirect based on role
        if user.role == "customer":
            return redirect(url_for("customer_portal"))
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@auth.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
