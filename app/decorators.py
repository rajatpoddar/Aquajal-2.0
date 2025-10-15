from functools import wraps
from flask import flash, redirect, url_for, abort, request
from flask_login import current_user
from app.models import Business, SupplierProfile, User
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
        
        # It's possible the user object is stale. Let's get the fresh one.
        user = User.query.get(current_user.id)

        # Check if a supplier profile exists, if not, create one.
        if not user.supplier_profile:
            profile = SupplierProfile(
                user_id=user.id,
                shop_name=f"{user.username}'s Shop",
                address=user.address or "Not specified"
            )
            db.session.add(profile)
            db.session.commit()
            flash('Your supplier profile has been automatically created. Please review and update your shop details.', 'info')
            # After creating, redirect to the same page to reload the user object
            return redirect(request.url)

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

def delivery_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'delivery':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function