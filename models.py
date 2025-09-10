# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(120))
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default="admin")  # admin or customer
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)
    # relationship set on Customer side

class Customer(db.Model):
    __tablename__ = "customer"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    address = db.Column(db.String(250))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="customer", uselist=False)

class MilkType(db.Model):
    __tablename__ = "milk_type"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)  # Cow / Buffalo
    default_rate = db.Column(db.Float, nullable=False)

class RateChart(db.Model):
    __tablename__ = "rate_chart"
    id = db.Column(db.Integer, primary_key=True)
    milk_type_id = db.Column(db.Integer, db.ForeignKey("milk_type.id"), nullable=False)
    fat_value = db.Column(db.Integer, nullable=False)   # 1..10
    rate = db.Column(db.Float, nullable=False)
    milk_type = db.relationship("MilkType", backref="rate_chart")

class Transaction(db.Model):
    __tablename__ = "transaction"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    milk_type_id = db.Column(db.Integer, db.ForeignKey("milk_type.id"), nullable=False)
    date_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    session = db.Column(db.String(12), nullable=False)   # Morning / Evening
    qty_liters = db.Column(db.Float, nullable=False)
    fat_value = db.Column(db.Float(precision=1), nullable=True)  # nullable -> default rate used if null, float with 1 decimal
    rate_applied = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    txn_type = db.Column(db.String(10), nullable=False)  # Sell (customer→us) / Purchase (we→customer)
    customer = db.relationship("Customer", backref="transactions")
    milk_type = db.relationship("MilkType")

class Bill(db.Model):
    __tablename__ = "bill"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    week_end = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer", backref="bills")
