# app.py
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Customer, MilkType, RateChart, Transaction, Bill
from auth import auth
from billing import billing
from datetime import datetime, date, time, timezone
import os
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "replace-with-a-strong-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    app.register_blueprint(auth)
    app.register_blueprint(billing)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.route("/")
    @login_required
    def dashboard():
        # different dashboards for admin and customer
        if current_user.role == "customer":
            return redirect(url_for("customer_portal"))
        # admin dashboard summary
        today = date.today()
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today, datetime.max.time())
        txns = Transaction.query.filter(Transaction.date_time >= start,
                                        Transaction.date_time <= end).all()
        total_collected = sum(t.qty_liters for t in txns if t.txn_type.lower() == "sell")
        total_sold = sum(t.qty_liters for t in txns if t.txn_type.lower() == "purchase")
        revenue = sum(t.total_amount for t in txns if t.txn_type.lower() == "sell")
        stats = {
            "today_liters": round(total_collected, 2),
            "today_sold": round(total_sold, 2),
            "today_revenue": round(revenue, 2)
        }
        return render_template("dashboard.html", stats=stats)

    @app.route("/customers")
    @login_required
    def customers_list():
        if current_user.role != "admin":
            flash("Not authorized", "error")
            return redirect(url_for("dashboard"))
        customers = Customer.query.order_by(Customer.name).all()
        return render_template("customers.html", customers=customers)

    @app.route("/customers/new", methods=["POST"])
    @login_required
    def add_customer():
        if current_user.role != "admin":
            flash("Not authorized", "error")
            return redirect(url_for("dashboard"))
        name = request.form.get("name")
        phone = request.form.get("phone")
        address = request.form.get("address")
        if not name:
            flash("Name required", "error")
            return redirect(url_for("customers_list"))
        cust = Customer(name=name, phone=phone, address=address)
        db.session.add(cust)
        db.session.commit()
        flash("Customer added", "success")
        return redirect(url_for("customers_list"))

    @app.route("/transactions")
    @login_required
    def transactions():
        if current_user.role == "customer":
            # show only customer transactions
            txns = Transaction.query.filter_by(customer_id=current_user.customer_id).order_by(Transaction.date_time.desc()).all()
        else:
            txns = Transaction.query.order_by(Transaction.date_time.desc()).limit(300).all()
        return render_template("transactions.html", txns=txns)

    def lookup_rate(milk_type_id, fat_value):
        # prefer exact fat value in RateChart, else MilkType.default_rate
        if fat_value is not None:
            rc = RateChart.query.filter_by(milk_type_id=milk_type_id, fat_value=fat_value).first()
            if rc:
                return rc.rate
        mt = MilkType.query.get(milk_type_id)
        return mt.default_rate if mt else 0.0
    
    @app.route("/rate-chart")
    @login_required
    def rate_chart_view():
        # get milk types
        cow = MilkType.query.filter_by(name="Cow").first()
        buff = MilkType.query.filter_by(name="Buffalo").first()

        # if db not seeded properly
        if not cow or not buff:
            flash("Milk types not found. Please run init-db.", "error")
            return redirect(url_for("dashboard"))

        # query rate chart by fat values
        cow_rates = (RateChart.query
                    .filter_by(milk_type_id=cow.id)
                    .order_by(RateChart.fat_value)
                    .all())
        buff_rates = (RateChart.query
                    .filter_by(milk_type_id=buff.id)
                    .order_by(RateChart.fat_value)
                    .all())

        return render_template(
            "rate_chart.html",
            cow_rates=cow_rates,
            buff_rates=buff_rates,
            cow=cow,
            buff=buff,
            title="Rate Chart"
        )


    @app.route("/transactions/new", methods=["GET", "POST"])
    @login_required
    def new_transaction():
        if current_user.role != "admin":
            flash("Only admin can record transactions", "error")
            return redirect(url_for("transactions"))

        milk_types = MilkType.query.order_by(MilkType.name).all()
        customers = Customer.query.order_by(Customer.name).all()

        if request.method == "POST":
            # --- parse/validate incoming form data ---
            try:
                customer_id = int(request.form.get("customer_id"))
                milk_type_id = int(request.form.get("milk_type_id"))
            except (TypeError, ValueError):
                flash("Invalid customer or milk type selection.", "error")
                return redirect(url_for("new_transaction"))

            session_val = request.form.get("session") or "Morning"

            # quantity
            try:
                qty = float(request.form.get("qty_liters") or 0)
            except ValueError:
                flash("Invalid quantity value.", "error")
                return redirect(url_for("new_transaction"))

            # fat (optional, float)
            fat_raw = request.form.get("fat_value")
            try:
                fat_value = float(fat_raw) if fat_raw not in (None, "") else None
            except ValueError:
                flash("Invalid fat value.", "error")
                return redirect(url_for("new_transaction"))

            txn_type = request.form.get("txn_type") or "Sell"

            # --- date handling: parse user date as IST, then convert to UTC-naive for DB ---
            txn_date_str = request.form.get("txn_date")
            try:
                if txn_date_str:
                    # parse date string, assume midnight local IST for that day
                    parsed_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date()
                    ist_dt = datetime.combine(parsed_date, time.min).replace(tzinfo=IST)
                else:
                    # use current instant in IST
                    ist_dt = datetime.now(IST)

                # Convert IST-aware datetime to UTC and drop tzinfo so it matches the
                # existing convention of storing UTC-naive datetimes (default=datetime.utcnow)
                utc_dt = ist_dt.astimezone(timezone.utc).replace(tzinfo=None)

            except ValueError:
                flash("Invalid date format. Use YYYY-MM-DD.", "error")
                return redirect(url_for("new_transaction"))

            # --- compute rate & total ---
            rate = lookup_rate(milk_type_id, fat_value)
            total = round(qty * rate, 2)

            # --- create transaction object (store UTC-naive datetime into date_time) ---
            txn = Transaction(
                customer_id=customer_id,
                milk_type_id=milk_type_id,
                date_time=utc_dt,       # store UTC-naive datetime for consistency with default
                session=session_val,
                qty_liters=qty,
                fat_value=fat_value,
                rate_applied=rate,
                total_amount=total,
                txn_type=txn_type
            )

            db.session.add(txn)
            db.session.commit()
            flash("Transaction recorded", "success")
            return redirect(url_for("transactions"))

        # GET: pass today's date in IST to template so the <input type="date"> defaults correctly
        today_ist = datetime.now(IST).date().strftime("%Y-%m-%d")
        return render_template(
            "new_transaction.html",
            milk_types=milk_types,
            customers=customers,
            today=today_ist
        )
    


    @app.cli.command("init-db")
    def init_db():
        with app.app_context():
            db.create_all()
            # seed default admin if not present
            if not User.query.filter_by(phone="admin").first():
                admin = User(phone="admin", name="Administrator", password_hash=generate_password_hash("adminpass"), role="admin")
                db.session.add(admin)
            # seed milk types and rates if empty
            if MilkType.query.count() == 0:
                cow = MilkType(name="Cow", default_rate=45.0)
                buff = MilkType(name="Buffalo", default_rate=60.0)
                db.session.add_all([cow, buff])
                db.session.commit()
                for fat in range(1, 11):
                    db.session.add(RateChart(milk_type_id=cow.id, fat_value=fat, rate=30 + fat * 2))
                    db.session.add(RateChart(milk_type_id=buff.id, fat_value=fat, rate=50 + fat * 2.5))
            db.session.commit()
            print("DB initialized and seeded.")

    # create tables automatically if file missing
    with app.app_context():
        db.create_all()

    return app

if __name__ == "__main__":
    from werkzeug.security import generate_password_hash
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
