# File: app/models.py

from app import db, login
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timedelta, date
from time import time
from flask import current_app
import jwt


class SubscriptionPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    regular_price = db.Column(db.Float, nullable=False)
    sale_price = db.Column(db.Float, nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_percentage = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    expiry_date = db.Column(db.DateTime, nullable=True)

class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    owner_name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True, index=True)
    location = db.Column(db.String(200), nullable=True)
    new_jar_price = db.Column(db.Float, default=150.0)
    new_dispenser_price = db.Column(db.Float, default=150.0)
    jar_stock = db.Column(db.Integer, default=0)
    dispenser_stock = db.Column(db.Integer, default=0)
    full_day_jar_count = db.Column(db.Integer, default=50) 
    half_day_jar_count = db.Column(db.Integer, default=1) 
    low_stock_threshold = db.Column(db.Integer, default=20)
    low_stock_threshold_dispenser = db.Column(db.Integer, default=5)

    
    employees = db.relationship('User', backref='business', lazy='dynamic', cascade="all, delete-orphan")
    customers = db.relationship('Customer', backref='business', lazy='dynamic', cascade="all, delete-orphan")
    product_sales = db.relationship('ProductSale', backref='business', lazy='dynamic', cascade="all, delete-orphan")
    payments = db.relationship('Payment', back_populates='business', lazy='dynamic', cascade="all, delete-orphan")
    purchase_orders = db.relationship('PurchaseOrder', backref='business', lazy='dynamic', cascade="all, delete-orphan")

    subscription_status = db.Column(db.String(20), default='trial')
    trial_ends_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=40))
    subscription_plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plan.id'), nullable=True)
    subscription_plan = db.relationship('SubscriptionPlan')
    subscription_ends_at = db.Column(db.DateTime, nullable=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(10), index=True, default='staff') # Roles: staff, manager, admin, supplier
    daily_wage = db.Column(db.Float, nullable=True)
    cash_balance = db.Column(db.Float, default=0.0)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=True)
    mobile_number = db.Column(db.String(15), nullable=True, unique=True)
    address = db.Column(db.String(200), nullable=True)
    id_proof_filename = db.Column(db.String(100), nullable=True)
    
    logs = db.relationship('DailyLog', backref='staff', lazy='dynamic', cascade="all, delete-orphan")
    expenses = db.relationship('Expense', backref='staff', lazy='dynamic', cascade="all, delete-orphan")
    handovers = db.relationship('CashHandover', foreign_keys='CashHandover.user_id', backref='staff', lazy='dynamic', cascade="all, delete-orphan")
    product_sales = db.relationship('ProductSale', backref='staff', lazy='dynamic', cascade="all, delete-orphan")
    supplier_profile = db.relationship('SupplierProfile', back_populates='user', uselist=False, cascade="all, delete-orphan")


    def get_id(self): return f'user-{self.id}'
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    
    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return None
        return User.query.get(id)


# --- NEW: Supplier-related models ---
class SupplierProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shop_name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(250), nullable=True)
    
    user = db.relationship('User', back_populates='supplier_profile')
    products = db.relationship('SupplierProduct', backref='supplier', lazy='dynamic', cascade="all, delete-orphan")
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy='dynamic', cascade="all, delete-orphan")

class SupplierProduct(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    manufacture_price = db.Column(db.Float, nullable=True)
    discount_percentage = db.Column(db.Integer, default=0)
    category = db.Column(db.String(50), nullable=True) # e.g., Jars, Dispensers, Chemicals, etc.
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier_profile.id'), nullable=False)
    
class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier_profile.id'), nullable=False)
    order_date = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    delivery_date = db.Column(db.Date, nullable=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=True)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pending') # e.g., Pending, Confirmed, Delivered
    items = db.relationship('PurchaseOrderItem', backref='order', lazy='dynamic', cascade="all, delete-orphan")

class PurchaseOrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('purchase_order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('supplier_product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_purchase = db.Column(db.Float, nullable=False) # Storing price at time of order

    product = db.relationship('SupplierProduct')
# ------------------------------------

class Customer(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    mobile_number = db.Column(db.String(15), nullable=False, index=True)
    email = db.Column(db.String(120), index=True, unique=True, nullable=True)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(10), default='customer')
    village = db.Column(db.String(100))
    area = db.Column(db.String(100))
    landmark = db.Column(db.String(200))
    note = db.Column(db.String(300), nullable=True)
    daily_jars = db.Column(db.Integer, default=1)
    price_per_jar = db.Column(db.Float, nullable=False, default=20.0)
    due_amount = db.Column(db.Float, default=0.0)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    
    logs = db.relationship('DailyLog', backref='customer', lazy='dynamic', cascade="all, delete-orphan")
    requests = db.relationship('JarRequest', backref='customer', lazy='dynamic', cascade="all, delete-orphan")
    bookings = db.relationship('EventBooking', backref='customer', lazy='dynamic', cascade="all, delete-orphan")
    invoices = db.relationship('Invoice', back_populates='customer', lazy='dynamic', cascade="all, delete-orphan")
    
    __table_args__ = (db.UniqueConstraint('mobile_number', 'business_id', name='uq_customer_mobile_business'),)

    def get_id(self): return f'customer-{self.id}'
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    business = db.relationship('Business', back_populates='payments')
    razorpay_order_id = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    razorpay_signature = db.Column(db.String(200))
    amount = db.Column(db.Float)
    status = db.Column(db.String(20)) # created, successful, failed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plan.id'))

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jars_delivered = db.Column(db.Integer, nullable=False)
    amount_collected = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    payment_status = db.Column(db.String(20), default='Paid') # Paid, Due
    origin = db.Column(db.String(20), default='staff_log', server_default='staff_log') # staff_log, customer_request
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
    payment_status = db.Column(db.String(20), default='Paid') # Paid, Due
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

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    issue_date = db.Column(db.Date, nullable=False, default=date.today)
    due_date = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Unpaid') # Unpaid, Paid, Overdue
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)
    
    customer = db.relationship('Customer', back_populates='invoices')
    items = db.relationship('InvoiceItem', backref='invoice', lazy='dynamic', cascade="all, delete-orphan")

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)

class EventBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    dispensers_booked = db.Column(db.Integer, default=0)
    event_date = db.Column(db.Date, nullable=False, index=True)
    amount = db.Column(db.Float, nullable=True)
    paid_to_manager = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='Pending', index=True) # Statuses: Pending, Confirmed, Delivered, Completed
    request_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_timestamp = db.Column(db.DateTime, nullable=True)
    collection_timestamp = db.Column(db.DateTime, nullable=True) 
    jars_returned = db.Column(db.Integer, nullable=True) 
    dispensers_returned = db.Column(db.Integer, nullable=True)
    final_amount = db.Column(db.Float, nullable=True) 
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    confirmed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    delivered_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    collected_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    confirmed_by = db.relationship("User", foreign_keys=[confirmed_by_id])
    delivered_by = db.relationship("User", foreign_keys=[delivered_by_id])
    collected_by = db.relationship("User", foreign_keys=[collected_by_id])

@login.user_loader
def load_user(user_id_string):
    try:
        user_type, user_id = user_id_string.split('-')
        user_id = int(user_id)
    except (ValueError, TypeError): return None
    if user_type == 'user': return User.query.get(user_id)
    elif user_type == 'customer': return Customer.query.get(user_id)
    return None

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shop_name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(250), nullable=True)
    user = db.relationship('User', backref='supplier', uselist=False)