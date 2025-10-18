# /water_supply_app/app/admin/routes.py

from flask import render_template, flash, redirect, url_for, abort, current_app, request
from flask_login import login_required, current_user, login_user
from app import db
from app.admin import bp
from app.models import User, Business, SubscriptionPlan, Coupon, Customer, SupplierProfile
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, PasswordField, SubmitField, FloatField, SelectField,
                     IntegerField, BooleanField, DateField, TextAreaField, SelectMultipleField)
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError, NumberRange, Email
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms.fields import DateField as WTDateField
from flask_babel import _, lazy_gettext as _l
from app.email import send_email
from sqlalchemy import func  # <-- THIS WAS THE MISSING IMPORT

from functools import wraps
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta


# --- Custom Decorator for Admin Access ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# --- Forms ---
class PlanForm(FlaskForm):
    name = StringField(_l('Plan Name'), validators=[DataRequired()])
    regular_price = FloatField(_l('Regular Price (₹)'), validators=[DataRequired(), NumberRange(min=0)])
    sale_price = FloatField(_l('Sale Price (₹)'), validators=[DataRequired(), NumberRange(min=0)])
    duration_days = IntegerField(_l('Duration (in days)'), validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField(_l('Save Plan'))

class CouponForm(FlaskForm):
    code = StringField(_l('Coupon Code'), validators=[DataRequired()])
    discount_percentage = IntegerField(_l('Discount Percentage (%%)'), validators=[DataRequired(), NumberRange(min=1, max=100)])
    is_active = BooleanField(_l('Active'), default=True)
    expiry_date = WTDateField(_l('Expiry Date (Optional)'), format='%Y-%m-%d', validators=[Optional()]) # Use WTDateField
    submit = SubmitField(_l('Save Coupon'))

    def __init__(self, original_code=None, *args, **kwargs):
        super(CouponForm, self).__init__(*args, **kwargs)
        self.original_code = original_code

    def validate_code(self, code):
        # Ensure code comparison is case-insensitive
        upper_code_data = code.data.upper() if code.data else None
        upper_original_code = self.original_code.upper() if self.original_code else None
        if upper_code_data and upper_code_data != upper_original_code:
            # Use func.upper() for database-side case-insensitive check
            coupon = Coupon.query.filter(func.upper(Coupon.code) == upper_code_data).first()
            if coupon:
                raise ValidationError(_('This coupon code already exists.'))

class BusinessSubscriptionForm(FlaskForm):
    subscription_plan_id = SelectField(_l('Assign Plan'), coerce=int, validators=[Optional()])
    subscription_ends_at = WTDateField(_l('Subscription Ends On'), format='%Y-%m-%d', validators=[Optional()]) # Use WTDateField
    submit_subscription = SubmitField(_l('Update Subscription'))

    def __init__(self, *args, **kwargs):
        super(BusinessSubscriptionForm, self).__init__(*args, **kwargs)
        self.subscription_plan_id.choices = [(0, _l('--- No Plan (Trial/Expired) ---'))] + \
                                            [(p.id, f"{p.name} ({p.duration_days} days)") for p in SubscriptionPlan.query.order_by('name').all()]


class BusinessForm(FlaskForm):
    name = StringField(_l('Business Name (e.g., Plant Location)'), validators=[DataRequired()])
    owner_name = StringField(_l('Owner Name'), validators=[Optional()])
    email = StringField(_l('Business Email'), validators=[Optional(), Email()])
    location = StringField(_l('Location / Address'), validators=[Optional()])
    new_jar_price = FloatField(_l('Default New Jar Price (₹)'), default=150.0, validators=[DataRequired()])
    new_dispenser_price = FloatField(_l('Default New Dispenser Price (₹)'), default=150.0, validators=[DataRequired()])
    submit = SubmitField(_l('Save Business'))

class AdminProfileForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField(_l('Email Address'), validators=[Optional(), Email()])
    mobile_number = StringField(_l('Mobile Number'), validators=[Optional(), Length(max=15)])
    password = PasswordField(_l('New Password (leave blank to keep current)'), validators=[Optional(), Length(min=6)])
    password2 = PasswordField(_l('Repeat New Password'), validators=[EqualTo('password', message=_l('Passwords must match.'))])
    submit = SubmitField(_l('Update Profile'))

    def __init__(self, original_username, original_mobile_number, original_email, *args, **kwargs):
        super(AdminProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_mobile_number = original_mobile_number
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter(func.lower(User.username) == username.data.lower()).first()
            if user is not None:
                raise ValidationError(_('This username is already taken.'))

    def validate_mobile_number(self, mobile_number):
        if mobile_number.data and mobile_number.data != self.original_mobile_number:
            user = User.query.filter_by(mobile_number=mobile_number.data).first()
            if user is not None:
                raise ValidationError(_('This mobile number is already registered.'))

    def validate_email(self, email):
        if email.data and email.data != self.original_email:
            user = User.query.filter(func.lower(User.email) == email.data.lower()).first()
            if user:
                raise ValidationError('This email address is already registered.')

# --- MultiCheckboxField for Email Form ---
class MultiCheckboxField(SelectMultipleField):
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()

class EmailForm(FlaskForm):
    recipient_type = SelectField(
        'Send To',
        choices=[
            ('all_managers', 'All Managers'),
            ('all_suppliers', 'All Suppliers'),
            ('all_customers', 'All Customers'),
            ('specific_users', 'Specific Staff/Managers/Suppliers'),
            ('specific_customers', 'Specific Customers')
        ],
        validators=[DataRequired()]
    )
    specific_emails = TextAreaField(
        'Specific Email Addresses (comma-separated)',
        description='Enter emails directly if selecting specific users/customers not in the lists below, or for external recipients.',
        validators=[Optional()]
    )
    user_recipients = MultiCheckboxField('Select Staff/Managers/Suppliers', coerce=int, validators=[Optional()])
    customer_recipients = MultiCheckboxField('Select Customers', coerce=int, validators=[Optional()])
    subject = StringField('Subject', validators=[DataRequired(), Length(max=120)])
    body = TextAreaField('Email Body (HTML allowed)', validators=[DataRequired()], render_kw={'rows': 10})
    submit = SubmitField('Send Email')

class UserForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(), Length(min=3, max=64)])
    shop_name = StringField(_l('Shop Name (for Suppliers)'), validators=[Optional(), Length(max=120)])
    mobile_number = StringField(_l('Mobile Number'), validators=[Optional(), Length(max=15)])
    address = TextAreaField(_l('Address'), validators=[Optional(), Length(max=200)])
    role = SelectField(_l('Role'), choices=[('staff', 'Staff'), ('manager', 'Manager'), ('supplier', 'Supplier')], validators=[DataRequired()])
    business_id = SelectField(_l('Assign to Business (for Staff/Manager)'), coerce=int, validators=[Optional()])
    daily_wage = FloatField(_l('Daily Wage (₹) (for Staff only)'), validators=[Optional()])
    password = PasswordField(_l('Password (leave blank for default: 123456)'), validators=[Optional(), Length(min=6)])
    password2 = PasswordField(_l('Repeat Password'), validators=[Optional(), EqualTo('password', message='Passwords must match if entered.')])
    id_proof = FileField(_l('ID Proof Image (JPG, PNG)'), validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg'], _l('Images only!'))
    ])
    submit = SubmitField(_l('Create User'))

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.business_id.choices = [(0, 'N/A')] + [(b.id, b.name) for b in Business.query.order_by('name').all()]

    def validate_username(self, username):
        user = User.query.filter(func.lower(User.username) == username.data.lower()).first()
        if user is not None:
            raise ValidationError(_('Please use a different username.'))

class EditUserForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired(), Length(min=3, max=64)])
    shop_name = StringField(_l('Shop Name (for Suppliers)'), validators=[Optional(), Length(max=120)])
    mobile_number = StringField(_l('Mobile Number'), validators=[Optional(), Length(max=15)])
    address = TextAreaField(_l('Address'), validators=[Optional(), Length(max=200)])
    role = SelectField(_l('Role'), choices=[('staff', 'Staff'), ('manager', 'Manager'), ('supplier', 'Supplier')], validators=[DataRequired()])
    business_id = SelectField(_l('Assign to Business (for Staff/Manager)'), coerce=int, validators=[Optional()])
    daily_wage = FloatField(_l('Daily Wage (₹) (for Staff only)'), validators=[Optional()])
    password = PasswordField(_l('New Password (leave blank to keep current)'), validators=[Optional(), Length(min=6)])
    id_proof = FileField(_l('ID Proof Image (JPG, PNG)'), validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg'], _l('Images only!'))
    ])
    submit = SubmitField(_l('Update User'))

    def __init__(self, original_username, original_mobile_number, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_mobile_number = original_mobile_number
        self.business_id.choices = [(0, 'N/A')] + [(b.id, b.name) for b in Business.query.order_by('name').all()]

    def validate_username(self, username):
        if username.data != self.original_username:
            if User.query.filter(func.lower(User.username) == username.data.lower()).first() or \
               Customer.query.filter(func.lower(Customer.username) == username.data.lower()).first():
                raise ValidationError(_('This username is already taken.'))

    def validate_mobile_number(self, mobile_number):
        if mobile_number.data and mobile_number.data != self.original_mobile_number:
            user = User.query.filter_by(mobile_number=mobile_number.data).first()
            if user is not None:
                raise ValidationError(_('This mobile number is already registered.'))


# --- Routes ---
@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Pagination parameters
    page_biz = request.args.get('page_biz', 1, type=int)
    page_users = request.args.get('page_users', 1, type=int)
    per_page = 5 # Items per page for lists, adjust as needed

    businesses_pagination = Business.query.order_by(Business.name).paginate(
        page=page_biz, per_page=per_page, error_out=False
    )

    users_pagination = User.query.filter(User.role.in_(['manager', 'staff', 'supplier'])).order_by(
        User.business_id, User.role, User.username).paginate(
        page=page_users, per_page=per_page, error_out=False
    )

    return render_template(
        'admin/dashboard.html',
        businesses_pagination=businesses_pagination, # Pass pagination object
        users_pagination=users_pagination,       # Pass pagination object
        title=_("Admin Dashboard")
    )

# --- Admin Profile ---
@bp.route('/profile', methods=['GET', 'POST'])
@login_required
@admin_required
def profile():
    form = AdminProfileForm(
        original_username=current_user.username,
        original_mobile_number=current_user.mobile_number,
        original_email=current_user.email,
        obj=current_user
    )
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.mobile_number = form.mobile_number.data
        current_user.email = form.email.data
        if form.password.data:
            current_user.set_password(form.password.data)
        db.session.commit()
        flash(_('Your profile has been updated.'), 'success')
        
        if current_user.username != form.username.data:
             login_user(current_user)
        return redirect(url_for('admin.profile'))
    return render_template('admin/profile_form.html', title=_("My Profile"), form=form)

# --- Business Management ---
@bp.route('/business/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_business():
    form = BusinessForm()
    if form.validate_on_submit():
        business = Business(
            name=form.name.data,
            owner_name=form.owner_name.data,
            email=form.email.data,
            location=form.location.data,
            new_jar_price=form.new_jar_price.data,
            new_dispenser_price=form.new_dispenser_price.data
            )
        db.session.add(business)
        db.session.commit()
        flash(_('Business "%(name)s" created successfully.', name=business.name))
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/business_form.html', form=form, title=_("Create New Business"), business=None)

@bp.route('/business/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_business(id):
    business = Business.query.get_or_404(id)
    form = BusinessForm(obj=business)
    sub_form = BusinessSubscriptionForm(obj=business)

    # Handle Business Details Update
    if form.submit.data and form.validate_on_submit():
        business.name = form.name.data
        business.owner_name = form.owner_name.data
        business.email = form.email.data
        business.location = form.location.data
        business.new_jar_price = form.new_jar_price.data
        business.new_dispenser_price = form.new_dispenser_price.data
        db.session.commit()
        flash(_('Business "%(name)s" details have been updated.', name=business.name), 'success')
        return redirect(url_for('admin.edit_business', id=id))

    # Handle Subscription Update
    if sub_form.submit_subscription.data and sub_form.validate():
        plan_id = sub_form.subscription_plan_id.data
        ends_at = sub_form.subscription_ends_at.data

        if plan_id > 0: # A plan is selected (0 is 'No Plan')
            business.subscription_plan_id = plan_id
            business.subscription_status = 'active'
            if ends_at:
                business.subscription_ends_at = datetime.combine(ends_at, datetime.min.time())
            else:
                plan = SubscriptionPlan.query.get(plan_id)
                if plan:
                    start_date = datetime.utcnow()
                    if business.subscription_ends_at and business.subscription_ends_at > start_date:
                        start_date = business.subscription_ends_at
                    business.subscription_ends_at = start_date + timedelta(days=plan.duration_days)
                else:
                    flash('Selected plan not found.', 'danger')
                    return redirect(url_for('admin.edit_business', id=id))
            flash(_('Subscription updated for "%(name)s".', name=business.name), 'success')
        else: # No plan is selected (value 0)
            business.subscription_plan_id = None
            business.subscription_status = 'expired'
            business.subscription_ends_at = None
            flash(_('Subscription removed for "%(name)s". Status set to expired.', name=business.name), 'warning')

        db.session.commit()
        return redirect(url_for('admin.edit_business', id=id))

    if business.subscription_ends_at:
        sub_form.subscription_ends_at.data = business.subscription_ends_at.date()

    return render_template('admin/business_form.html', form=form, sub_form=sub_form, business=business, title=_("Edit Business"))


@bp.route('/business/reset_stock/<int:id>', methods=['POST'])
@login_required
@admin_required
def reset_stock(id):
    business = Business.query.get_or_404(id)
    business.jar_stock = 0
    business.dispenser_stock = 0
    db.session.commit()
    flash(_('Stock for "%(name)s" has been reset to zero.', name=business.name), 'success')
    return redirect(url_for('admin.dashboard'))

# --- User Management ---
@bp.route('/user/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = UserForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            role=form.role.data,
            mobile_number=form.mobile_number.data,
            address=form.address.data
        )
        if form.role.data in ['staff', 'manager'] and form.business_id.data > 0:
            user.business_id = form.business_id.data
        elif form.role.data in ['staff', 'manager']:
             flash('Staff/Manager must be assigned to a business.', 'warning')
             return render_template('admin/user_form.html', form=form, title=_("Add New User"), user=None)


        if form.role.data == 'staff':
            user.daily_wage = form.daily_wage.data

        password_to_set = form.password.data if form.password.data else '123456'
        user.set_password(password_to_set)

        db.session.add(user)
        try:
            db.session.commit()

            if form.id_proof.data:
                f = form.id_proof.data
                filename = secure_filename(f"{user.id}_{user.username}_{f.filename}")
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                f.save(filepath)
                user.id_proof_filename = filename
                db.session.commit()

            if form.role.data == 'supplier':
                supplier_profile = SupplierProfile(
                    user_id=user.id,
                    shop_name=form.shop_name.data if form.shop_name.data else f"{user.username}'s Shop",
                    address=form.address.data
                )
                db.session.add(supplier_profile)
                db.session.commit()

            flash(_('User "%(username)s" has been created.', username=user.username))
            if not form.password.data:
                flash(_('Default password "123456" has been set for this user.'), 'info')

            return redirect(url_for('admin.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {e}', 'danger')


    return render_template('admin/user_form.html', form=form, title=_("Add New User"), user=None)


@bp.route('/user/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        abort(403)
    form = EditUserForm(original_username=user.username, original_mobile_number=user.mobile_number, obj=user)

    if form.validate_on_submit():
        user.username = form.username.data
        user.mobile_number = form.mobile_number.data
        user.address = form.address.data
        original_role = user.role
        user.role = form.role.data

        if user.role in ['staff', 'manager']:
            user.business_id = form.business_id.data if form.business_id.data != 0 else None
            if not user.business_id:
                 flash('Staff/Manager must be assigned to a business.', 'warning')
                 return render_template('admin/user_form.html', form=form, user=user, title=_("Edit User"))
        else:
            user.business_id = None

        if user.role == 'staff':
            user.daily_wage = form.daily_wage.data
        else:
            user.daily_wage = None

        if form.password.data:
            user.set_password(form.password.data)

        if form.id_proof.data:
            if user.id_proof_filename:
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], user.id_proof_filename))
                except OSError:
                    pass
            f = form.id_proof.data
            filename = secure_filename(f"{user.id}_{user.username}_{f.filename}")
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            user.id_proof_filename = filename

        if user.role == 'supplier':
            supplier_profile = user.supplier_profile or SupplierProfile(user_id=user.id)
            supplier_profile.shop_name = form.shop_name.data if form.shop_name.data else f"{user.username}'s Shop"
            supplier_profile.address = form.address.data
            if not user.supplier_profile:
                db.session.add(supplier_profile)
        elif original_role == 'supplier' and user.supplier_profile:
             pass

        try:
            db.session.commit()
            flash(_('User "%(username)s" has been updated.', username=user.username))
            return redirect(url_for('admin.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {e}', 'danger')

    if request.method == 'GET':
        form.role.data = user.role
        form.business_id.data = user.business_id or 0
        form.daily_wage.data = user.daily_wage
        form.address.data = user.address
        if user.role == 'supplier' and user.supplier_profile:
            form.shop_name.data = user.supplier_profile.shop_name

    return render_template('admin/user_form.html', form=form, user=user, title=_("Edit User"))


@bp.route('/user/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        flash(_('Cannot delete the admin user.'))
        return redirect(url_for('admin.dashboard'))
    username_deleted = user.username
    try:
        if user.id_proof_filename:
             try:
                 os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], user.id_proof_filename))
             except OSError:
                 pass
        
        db.session.delete(user)
        db.session.commit()
        flash(_('User "%(username)s" has been deleted.', username=username_deleted))
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {e}', 'danger')
    return redirect(url_for('admin.dashboard'))


# --- SaaS Management Routes ---

# Subscription Plans
@bp.route('/plans')
@login_required
@admin_required
def list_plans():
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.duration_days).all()
    return render_template('admin/subscription_plans.html', plans=plans, title=_("Subscription Plans"))

@bp.route('/plans/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_plan():
    form = PlanForm()
    if form.validate_on_submit():
        plan = SubscriptionPlan(name=form.name.data, regular_price=form.regular_price.data,
                                sale_price=form.sale_price.data, duration_days=form.duration_days.data)
        db.session.add(plan)
        db.session.commit()
        flash(_('New subscription plan has been created.'), 'success')
        return redirect(url_for('admin.list_plans'))
    return render_template('admin/plan_form.html', form=form, title=_("Add New Plan"))

@bp.route('/plans/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_plan(id):
    plan = SubscriptionPlan.query.get_or_404(id)
    form = PlanForm(obj=plan)
    if form.validate_on_submit():
        plan.name = form.name.data
        plan.regular_price = form.regular_price.data
        plan.sale_price = form.sale_price.data
        plan.duration_days = form.duration_days.data
        db.session.commit()
        flash(_('Subscription plan has been updated.'), 'success')
        return redirect(url_for('admin.list_plans'))
    return render_template('admin/plan_form.html', form=form, title=_("Edit Plan"))

@bp.route('/plans/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_plan(id):
    plan = SubscriptionPlan.query.get_or_404(id)
    if Business.query.filter_by(subscription_plan_id=id).first():
        flash(_('Cannot delete plan. It is currently assigned to one or more businesses.'), 'danger')
    else:
        db.session.delete(plan)
        db.session.commit()
        flash(_('Plan "%(name)s" has been deleted.', name=plan.name), 'success')
    return redirect(url_for('admin.list_plans'))


# Coupons
@bp.route('/coupons')
@login_required
@admin_required
def list_coupons():
    coupons = Coupon.query.order_by(Coupon.is_active.desc(), Coupon.code).all()
    return render_template('admin/coupons.html', coupons=coupons, title=_("Manage Coupons"))

@bp.route('/coupons/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_coupon():
    form = CouponForm()
    if form.validate_on_submit():
        expiry = form.expiry_date.data
        coupon = Coupon(code=form.code.data.upper(), discount_percentage=form.discount_percentage.data,
                        is_active=form.is_active.data,
                        expiry_date=datetime.combine(expiry, datetime.min.time()) if expiry else None)
        db.session.add(coupon)
        db.session.commit()
        flash(_('New coupon has been created.'), 'success')
        return redirect(url_for('admin.list_coupons'))
    return render_template('admin/coupon_form.html', form=form, title=_("Add New Coupon"))

@bp.route('/coupons/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_coupon(id):
    coupon = Coupon.query.get_or_404(id)
    form = CouponForm(obj=coupon, original_code=coupon.code)
    if form.validate_on_submit():
        coupon.code = form.code.data.upper()
        coupon.discount_percentage = form.discount_percentage.data
        coupon.is_active = form.is_active.data
        expiry = form.expiry_date.data
        coupon.expiry_date = datetime.combine(expiry, datetime.min.time()) if expiry else None
        db.session.commit()
        flash(_('Coupon has been updated.'), 'success')
        return redirect(url_for('admin.list_coupons'))
    if request.method == 'GET' and coupon.expiry_date:
        form.expiry_date.data = coupon.expiry_date.date()
    return render_template('admin/coupon_form.html', form=form, title=_("Edit Coupon"))

@bp.route('/coupons/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_coupon(id):
    coupon = Coupon.query.get_or_404(id)
    code_deleted = coupon.code
    db.session.delete(coupon)
    db.session.commit()
    flash(_('Coupon "%(code)s" has been deleted.', code=code_deleted), 'success')
    return redirect(url_for('admin.list_coupons'))

# --- DANGEROUS: Business Deletion ---
@bp.route('/business/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_business(id):
    business = Business.query.get_or_404(id)
    business_name_deleted = business.name
    try:
        db.session.delete(business)
        db.session.commit()
        flash(_('Business "%(name)s" and all of its associated data have been permanently deleted.', name=business_name_deleted), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('Error deleting business: %(error)s', error=str(e)), 'danger')
    return redirect(url_for('admin.dashboard'))

# --- NEW: Custom Email Route Implementation ---
@bp.route('/send-custom-email', methods=['GET', 'POST'])
@login_required
@admin_required
def send_custom_email():
    form = EmailForm()
    # Populate choices dynamically, ensuring users/customers have emails
    form.user_recipients.choices = [(u.id, f"{u.username} ({u.role}) - {u.email}")
                                    for u in User.query.filter(User.role != 'admin', User.email != None, User.email != '').order_by(User.role, User.username)]
    form.customer_recipients.choices = [(c.id, f"{c.name} ({c.village}) - {c.email}")
                                        for c in Customer.query.filter(Customer.email != None, Customer.email != '').order_by(Customer.name)]

    if form.validate_on_submit():
        recipients_set = set() # Use a set to avoid duplicates
        recipient_type = form.recipient_type.data
        subject = form.subject.data
        body_html = form.body.data
        text_body = "Please view this email in an HTML-compatible client."

        # Collect email addresses based on selection
        if recipient_type == 'all_managers':
            recipients_set.update([u.email for u in User.query.filter(User.role == 'manager', User.email != None, User.email != '').all()])
        elif recipient_type == 'all_suppliers':
            recipients_set.update([u.email for u in User.query.filter(User.role == 'supplier', User.email != None, User.email != '').all()])
        elif recipient_type == 'all_customers':
            recipients_set.update([c.email for c in Customer.query.filter(Customer.email != None, Customer.email != '').all()])
        elif recipient_type == 'specific_users':
            user_ids = form.user_recipients.data
            recipients_set.update([u.email for u in User.query.filter(User.id.in_(user_ids), User.email != None, User.email != '').all()])
        elif recipient_type == 'specific_customers':
            customer_ids = form.customer_recipients.data
            recipients_set.update([c.email for c in Customer.query.filter(Customer.id.in_(customer_ids), Customer.email != None, Customer.email != '').all()])

        # Add manually entered emails
        if form.specific_emails.data:
            manual_emails = [email.strip() for email in form.specific_emails.data.split(',') if email.strip() and '@' in email]
            recipients_set.update(manual_emails)

        valid_recipients = list(recipients_set)

        if not valid_recipients:
            flash('No valid recipients found based on your selection. Ensure selected users/customers have email addresses.', 'warning')
        else:
            try:
                # Basic HTML wrapping for content provided by admin
                wrapped_html_body = render_template('email/custom_admin_email_wrapper.html', email_body_content=body_html, subject=subject)

                # Consider using a background task queue (like Celery) for sending many emails
                # For simplicity here, sending sequentially:
                for email_addr in valid_recipients:
                    send_email(
                        subject=subject,
                        sender=current_app.config['ADMINS'][0],
                        recipients=[email_addr],
                        text_body=text_body, # Generate a better text version if possible
                        html_body=wrapped_html_body
                    )
                flash(f'Email sent successfully to {len(valid_recipients)} recipient(s).', 'success')
                return redirect(url_for('admin.dashboard'))
            except Exception as e:
                current_app.logger.error(f"Email sending failed: {e}") # Log the error
                flash(f'An error occurred while sending emails: {str(e)}', 'danger')

    return render_template('admin/send_email.html', title='Send Custom Email', form=form)