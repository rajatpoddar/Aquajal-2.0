# File: app/__init__.py
from flask import Flask, redirect, url_for, session, request, current_app
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
# The missing 'login_required' has been re-added here.
from flask_login import LoginManager, current_user, login_required
from flask_apscheduler import APScheduler
from sqlalchemy import MetaData
from zoneinfo import ZoneInfo
import os
import calendar
from flask_mail import Mail
from flask_babel import Babel, _
from flask_moment import Moment

# --- Naming convention for database constraints ---
metadata = MetaData(naming_convention={
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
})

# --- Initialize extensions ---
db = SQLAlchemy(metadata=metadata)
migrate = Migrate()
login = LoginManager()
scheduler = APScheduler()
mail = Mail()
babel = Babel()
moment = Moment()

# --- Set the single, unified login view ---
login.login_view = 'auth.login'

# This function selects the language for the user
def get_locale():
    return session.get('language', 'en')

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    mail.init_app(app)
    # Correctly initialize Babel with the locale_selector function
    babel.init_app(app, locale_selector=get_locale)
    moment.init_app(app)

    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

    from .wages import deduct_daily_wages
    
    # Your original scheduler logic is preserved
    if not scheduler.running:
        scheduler.init_app(app)
        if not scheduler.get_job('deduct-wages'):
            scheduler.add_job(id='deduct-wages', func=deduct_daily_wages, args=[app], trigger='cron', hour=20, minute=0)
        scheduler.start()

    # --- Register Blueprints ---
    from app.errors import bp as errors_bp
    app.register_blueprint(errors_bp)
    
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.customers import bp as customers_bp
    app.register_blueprint(customers_bp, url_prefix='/customers')
    
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    from app.delivery import bp as delivery_bp
    app.register_blueprint(delivery_bp)
    
    from app.manager import bp as manager_bp
    app.register_blueprint(manager_bp, url_prefix='/manager')
    
    from app.sales import bp as sales_bp
    app.register_blueprint(sales_bp, url_prefix='/sales')
    
    from app.customer import bp as customer_bp
    app.register_blueprint(customer_bp, url_prefix='/customer')
    
    from app.billing import bp as billing_bp
    app.register_blueprint(billing_bp, url_prefix='/billing')
    
    from app.public import bp as public_bp
    app.register_blueprint(public_bp)
    
    from app.invoices import bp as invoices_bp
    app.register_blueprint(invoices_bp, url_prefix='/invoices')

    from app.supplier import bp as supplier_bp
    app.register_blueprint(supplier_bp, url_prefix='/supplier')
    
    from app.models import User, Customer
    from datetime import datetime

    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

    @app.route('/home')
    @login_required
    def home():
        if isinstance(current_user, Customer):
            return redirect(url_for('customer.dashboard'))

        if isinstance(current_user, User):
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'manager':
                return redirect(url_for('manager.dashboard'))
            elif current_user.role == 'staff':
                return redirect(url_for('delivery.dashboard'))
            elif current_user.role == 'supplier':
                return redirect(url_for('supplier.dashboard'))

        return redirect(url_for('auth.login'))

    from . import seeder
    seeder.init_app(app)

    # --- CUSTOM TEMPLATE FILTERS ---
    @app.template_filter('to_ist')
    def to_ist_filter(utc_dt):
        if utc_dt is None:
            return ''
        return utc_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Kolkata"))

    @app.template_filter('month_name')
    def month_name_filter(month_number):
        try:
            return calendar.month_name[month_number]
        except (IndexError, TypeError):
            return ''

    return app

from app import models