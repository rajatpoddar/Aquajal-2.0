from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user
from app.models import Business
from datetime import datetime
from app import db

def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'manager']:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# --- NEW: Supplier Required Decorator ---
def supplier_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'supplier':
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function
# --------------------------------------

def subscription_required(f):
    """
    Ensures the manager's business has an active subscription or is in a trial period.
    This decorator should be placed AFTER @login_required.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role == 'admin':
            return f(*args, **kwargs)

        # Skip subscription checks for suppliers and other roles
        if current_user.role != 'manager':
             return f(*args, **kwargs)

        business = Business.query.get(current_user.business_id)
        if not business:
            flash("You are not associated with a business.", "danger")
            return redirect(url_for('auth.logout'))

        is_active = False
        now = datetime.utcnow()

        if business.subscription_status == 'active' and business.subscription_ends_at and business.subscription_ends_at > now:
            is_active = True
        elif business.subscription_status == 'trial' and business.trial_ends_at and business.trial_ends_at > now:
            is_active = True

        if not is_active:
            if business.subscription_status == 'trial':
                business.subscription_status = 'expired'
                db.session.commit()
            return redirect(url_for('billing.expired'))
            
        return f(*args, **kwargs)
    return decorated_function