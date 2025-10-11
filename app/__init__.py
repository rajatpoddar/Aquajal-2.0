# /water_supply_app/app/__init__.py

from flask import Flask, redirect, url_for, request # <-- Add request
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_apscheduler import APScheduler
from sqlalchemy import MetaData
from zoneinfo import ZoneInfo
import os

metadata = MetaData(naming_convention={
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
})

db = SQLAlchemy(metadata=metadata)
migrate = Migrate()
login = LoginManager()
scheduler = APScheduler()

# --- REVERT TO THE SIMPLE LOGIN VIEW ---
login.login_view = 'auth.login'

# --- REMOVED this line: login.login_view = 'auth.login' ---

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)

    with app.app_context():
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

    from .wages import deduct_daily_wages
    
    scheduler.init_app(app)
    if not scheduler.get_job('deduct-wages'):
        scheduler.add_job(id='deduct-wages', func=deduct_daily_wages, args=[app], trigger='cron', hour=20, minute=0)
    scheduler.start()

    # Register Blueprints
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    from app.customers.routes import bp as customers_bp
    app.register_blueprint(customers_bp, url_prefix='/customers')
    from app.admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    from app.delivery.routes import bp as delivery_bp
    app.register_blueprint(delivery_bp)
    from app.manager.routes import bp as manager_bp
    app.register_blueprint(manager_bp, url_prefix='/manager')
    from app.sales.routes import bp as sales_bp
    app.register_blueprint(sales_bp, url_prefix='/sales')
    from app.customer.routes import bp as customer_bp
    app.register_blueprint(customer_bp, url_prefix='/customer')

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if hasattr(current_user, 'role'):
                if current_user.role == 'admin':
                    return redirect(url_for('admin.dashboard'))
                elif current_user.role == 'manager':
                    return redirect(url_for('manager.dashboard'))
                elif current_user.role == 'customer':
                    return redirect(url_for('customer.dashboard'))
                else: # Staff
                    return redirect(url_for('delivery.dashboard'))
        return redirect(url_for('auth.login'))

    from . import seeder
    seeder.init_app(app)

    @app.template_filter('to_ist')
    def to_ist_filter(utc_dt):
        if utc_dt is None:
            return ''
        return utc_dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Kolkata"))

    return app

from app import models