# /water_supply_app/app/models.py

from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    new_jar_price = db.Column(db.Float, default=150.0)
    new_dispenser_price = db.Column(db.Float, default=1500.0)
    jar_stock = db.Column(db.Integer, default=0)
    dispenser_stock = db.Column(db.Integer, default=0)
    employees = db.relationship('User', backref='business', lazy='dynamic')
    customers = db.relationship('Customer', backref='business', lazy='dynamic')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(10), index=True, default='staff')
    daily_wage = db.Column(db.Float, nullable=True)
    cash_balance = db.Column(db.Float, default=0.0)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)
    mobile_number = db.Column(db.String(15), nullable=True, unique=True)
    address = db.Column(db.String(200), nullable=True)
    id_proof_filename = db.Column(db.String(100), nullable=True)
    logs = db.relationship('DailyLog', backref='staff', lazy='dynamic')
    expenses = db.relationship('Expense', backref='staff', lazy='dynamic')
    handovers = db.relationship('CashHandover', foreign_keys='CashHandover.user_id', backref='staff', lazy='dynamic')
    product_sales = db.relationship('ProductSale', backref='staff', lazy='dynamic')
    def get_id(self): return f'user-{self.id}'
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Customer(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    mobile_number = db.Column(db.String(15), nullable=False, index=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(10), default='customer')
    village = db.Column(db.String(100))
    area = db.Column(db.String(100))
    landmark = db.Column(db.String(200))
    daily_jars = db.Column(db.Integer, default=1)
    price_per_jar = db.Column(db.Float, nullable=False, default=20.0)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    logs = db.relationship('DailyLog', backref='customer', lazy='dynamic')
    requests = db.relationship('JarRequest', backref='customer', lazy='dynamic')
    bookings = db.relationship('EventBooking', backref='customer', lazy='dynamic')
    __table_args__ = (db.UniqueConstraint('mobile_number', 'business_id', name='uq_customer_mobile_business'),)
    def get_id(self): return f'customer-{self.id}'
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jars_delivered = db.Column(db.Integer, nullable=False)
    amount_collected = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
class CashHandover(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    manager = db.relationship("User", foreign_keys=[manager_id])
class ProductSale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_per_item = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    customer_name = db.Column(db.String(120))
    customer_mobile = db.Column(db.String(15))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'))
class JarRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='Pending', index=True)
    request_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_timestamp = db.Column(db.DateTime, nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    delivered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
class EventBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    event_date = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Float, nullable=True)
    paid_to_manager = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='Pending', index=True)
    request_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_timestamp = db.Column(db.DateTime, nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    delivered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

@login.user_loader
def load_user(user_id_string):
    try:
        user_type, user_id = user_id_string.split('-')
        user_id = int(user_id)
    except (ValueError, TypeError): return None
    if user_type == 'user': return User.query.get(user_id)
    elif user_type == 'customer': return Customer.query.get(user_id)
    return None