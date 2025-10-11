import click
from flask.cli import with_appcontext
from . import db
from .models import Business, User

@click.command('seed-db')
@with_appcontext
def seed_db_command():
    """Creates a default business, admin, manager, and staff user."""
    
    # Check if data already exists to prevent duplicates
    if Business.query.first() or User.query.first():
        print("Database already has data. Aborting seed.")
        return

    print("Creating default business and users...")

    # Create your first business
    b1 = Business(name='Main Plant', new_jar_price=150, new_dispenser_price=1500)
    db.session.add(b1)
    db.session.commit() # Commit here to get b1.id for the users

    # Create an admin user
    u_admin = User(username='admin', role='admin')
    u_admin.set_password('adminpass')
    db.session.add(u_admin)

    # Create a manager for the 'Main Plant'
    u_manager = User(username='manager', role='manager', business_id=b1.id)
    u_manager.set_password('managerpass')
    db.session.add(u_manager)

    # Create a staff member for the 'Main Plant'
    u_staff = User(username='staff', role='staff', business_id=b1.id, daily_wage=300)
    u_staff.set_password('staffpass')
    db.session.add(u_staff)

    db.session.commit()
    print("✅ Business, admin, manager, and staff created successfully!")

def init_app(app):
    """Register the CLI command with the Flask app."""
    app.cli.add_command(seed_db_command)