# /water_supply_app/app/seeder.py

import click
from flask.cli import with_appcontext
from . import db
from .models import Business, User, SubscriptionPlan

@click.command('seed-db')
@with_appcontext
def seed_db_command():
    """Creates default data if it doesn't already exist."""

    # --- Seed Admin User (Ensures admin always exists) ---
    if not User.query.filter_by(role='admin').first():
        print("Admin user not found. Creating default admin...")
        u_admin = User(username='admin', role='admin', email='admin@example.com')
        u_admin.set_password('adminpass')
        db.session.add(u_admin)
        db.session.commit()
        print("✅ Admin user created with username 'admin' and password 'adminpass'.")
    else:
        print("Admin user already exists. Skipping.")
    
    # --- Seed Subscription Plans ---
    if not SubscriptionPlan.query.first():
        print("Creating default subscription plans...")
        plans = [
            SubscriptionPlan(name='Monthly', regular_price=499, sale_price=299, duration_days=30),
            SubscriptionPlan(name='Half-Yearly', regular_price=2999, sale_price=1999, duration_days=182),
            SubscriptionPlan(name='Yearly', regular_price=5999, sale_price=2999, duration_days=365)
        ]
        db.session.bulk_save_objects(plans)
        db.session.commit()
        print("✅ Subscription plans created.")
    else:
        print("Subscription plans already exist. Skipping.")

    # --- Seed Initial Business/Manager/Staff (Only if no businesses exist) ---
    if not Business.query.first():
        print("No businesses found. Creating default business, manager, and staff...")

        b1 = Business(name='Main Plant', new_jar_price=150, new_dispenser_price=150)
        db.session.add(b1)
        db.session.commit()

        u_manager = User(username='manager', role='manager', business_id=b1.id)
        u_manager.set_password('managerpass')
        db.session.add(u_manager)

        u_staff = User(username='staff', role='staff', business_id=b1.id, daily_wage=300)
        u_staff.set_password('staffpass')
        db.session.add(u_staff)
        
        db.session.commit()
        print("✅ Default business, manager, and staff created successfully!")
    else:
        print("Business data already exists. Skipping initial business seed.")

def init_app(app):
    """Register the CLI command with the Flask app."""
    app.cli.add_command(seed_db_command)