# /water_supply_app/app/admin/routes.py

from flask import render_template, flash, redirect, url_for, abort, current_app
from flask_login import login_required, current_user, login_user
from app import db
from app.admin import bp
from app.models import User, Business, SubscriptionPlan, Coupon, Customer
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, FloatField, SelectField, IntegerField, BooleanField, DateField, TextAreaField
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError, NumberRange, Email
from wtforms.fields import DateField as WTDateField

from functools import wraps
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta


# --- Custom Decorator for Admin Access ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# --- Forms ---
class PlanForm(FlaskForm):
    name = StringField('Plan Name', validators=[DataRequired()])
    regular_price = FloatField('Regular Price (₹)', validators=[DataRequired(), NumberRange(min=0)])
    sale_price = FloatField('Sale Price (₹)', validators=[DataRequired(), NumberRange(min=0)])
    duration_days = IntegerField('Duration (in days)', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Save Plan')

class CouponForm(FlaskForm):
    code = StringField('Coupon Code', validators=[DataRequired()])
    discount_percentage = IntegerField('Discount Percentage (%)', validators=[DataRequired(), NumberRange(min=1, max=100)])
    is_active = BooleanField('Active', default=True)
    expiry_date = DateField('Expiry Date (Optional)', validators=[Optional()])
    submit = SubmitField('Save Coupon')

    def __init__(self, original_code=None, *args, **kwargs):
        super(CouponForm, self).__init__(*args, **kwargs)
        self.original_code = original_code

    def validate_code(self, code):
        if code.data.upper() != self.original_code:
            coupon = Coupon.query.filter(Coupon.code == code.data.upper()).first()
            if coupon:
                raise ValidationError('This coupon code already exists.')

class BusinessSubscriptionForm(FlaskForm):
    subscription_plan_id = SelectField('Assign Plan', coerce=int, validators=[Optional()])
    subscription_ends_at = WTDateField('Subscription Ends On', format='%Y-%m-%d', validators=[Optional()])
    submit_subscription = SubmitField('Update Subscription')

    def __init__(self, *args, **kwargs):
        super(BusinessSubscriptionForm, self).__init__(*args, **kwargs)
        self.subscription_plan_id.choices = [(0, '--- No Plan (Trial/Expired) ---')] + \
                                            [(p.id, f"{p.name} ({p.duration_days} days)") for p in SubscriptionPlan.query.order_by('name').all()]


class BusinessForm(FlaskForm):
    name = StringField('Business Name (e.g., Plant Location)', validators=[DataRequired()])
    owner_name = StringField('Owner Name', validators=[Optional()])
    email = StringField('Business Email', validators=[Optional(), Email()])
    location = StringField('Location / Address', validators=[Optional()])
    new_jar_price = FloatField('Default New Jar Price (₹)', default=150.0, validators=[DataRequired()])
    new_dispenser_price = FloatField('Default New Dispenser Price (₹)', default=1500.0, validators=[DataRequired()])
    submit = SubmitField('Save Business')

class AdminProfileForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    password = PasswordField('New Password (leave blank to keep current)', validators=[Optional(), Length(min=6)])
    password2 = PasswordField('Repeat New Password', validators=[EqualTo('password', message='Passwords must match.')])
    submit = SubmitField('Update Profile')

    def __init__(self, original_username, original_mobile_number, *args, **kwargs):
        super(AdminProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_mobile_number = original_mobile_number

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('This username is already taken.')

    def validate_mobile_number(self, mobile_number):
        if mobile_number.data and mobile_number.data != self.original_mobile_number:
            user = User.query.filter_by(mobile_number=self.mobile_number.data).first()
            if user is not None:
                raise ValidationError('This mobile number is already registered.')


class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    address = TextAreaField('Address', validators=[Optional(), Length(max=200)])
    role = SelectField('Role', choices=[('staff', 'Staff'), ('manager', 'Manager')], validators=[DataRequired()])
    business_id = SelectField('Assign to Business', coerce=int, validators=[DataRequired()])
    daily_wage = FloatField('Daily Wage (₹)', validators=[Optional()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    id_proof = FileField('ID Proof Image (JPG, PNG)', validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])
    submit = SubmitField('Create User')

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.business_id.choices = [(b.id, b.name) for b in Business.query.order_by('name').all()]

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    address = StringField('Address', validators=[Optional(), Length(max=200)])
    role = SelectField('Role', choices=[('staff', 'Staff'), ('manager', 'Manager')], validators=[DataRequired()])
    business_id = SelectField('Assign to Business', coerce=int, validators=[DataRequired()])
    daily_wage = FloatField('Daily Wage (₹) (for Staff only)', validators=[Optional()])
    password = PasswordField('New Password (leave blank to keep current)', validators=[Optional(), Length(min=6)])
    id_proof = FileField('ID Proof Image (JPG, PNG)', validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])
    submit = SubmitField('Update User')

    def __init__(self, original_username, original_mobile_number, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_mobile_number = original_mobile_number
        self.business_id.choices = [(b.id, b.name) for b in Business.query.order_by('name').all()]

    def validate_username(self, username):
        if username.data != self.original_username:
            if User.query.filter_by(username=username.data).first() or \
               Customer.query.filter_by(username=username.data).first():
                raise ValidationError('This username is already taken.')

    def validate_mobile_number(self, mobile_number):
        if mobile_number.data and mobile_number.data != self.original_mobile_number:
            user = User.query.filter_by(mobile_number=mobile_number.data).first()
            if user is not None:
                raise ValidationError('This mobile number is already registered.')


# --- Routes ---
@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    businesses = Business.query.order_by(Business.name).all()
    users = User.query.filter(User.role.in_(['manager', 'staff'])).order_by(User.business_id, User.role, User.username).all()
    return render_template('admin/dashboard.html', businesses=businesses, users=users, title="Admin Dashboard")

# --- Admin Profile ---
@bp.route('/profile', methods=['GET', 'POST'])
@login_required
@admin_required
def profile():
    form = AdminProfileForm(
        original_username=current_user.username, 
        original_mobile_number=current_user.mobile_number, 
        obj=current_user
    )
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.mobile_number = form.mobile_number.data
        if form.password.data:
            current_user.set_password(form.password.data)
        db.session.commit()
        flash('Your profile has been updated.', 'success')
        # Re-login the user to update the session with the new username if it changed
        login_user(current_user)
        return redirect(url_for('admin.profile'))
    return render_template('admin/profile_form.html', title="My Profile", form=form)

# --- Business Management ---
@bp.route('/business/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_business():
    form = BusinessForm()
    if form.validate_on_submit():
        business = Business(name=form.name.data, location=form.location.data, new_jar_price=form.new_jar_price.data, new_dispenser_price=form.new_dispenser_price.data)
        db.session.add(business)
        db.session.commit()
        flash(f'Business "{business.name}" created successfully.')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/business_form.html', form=form, title="Create New Business", business=None)

@bp.route('/business/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_business(id):
    business = Business.query.get_or_404(id)
    form = BusinessForm(obj=business)
    sub_form = BusinessSubscriptionForm(obj=business)

    if form.submit.data and form.validate_on_submit():
        business.name = form.name.data
        business.owner_name = form.owner_name.data
        business.email = form.email.data
        business.location = form.location.data
        business.new_jar_price = form.new_jar_price.data
        business.new_dispenser_price = form.new_dispenser_price.data
        db.session.commit()
        flash(f'Business "{business.name}" details have been updated.', 'success')
        return redirect(url_for('admin.edit_business', id=id))

    if sub_form.submit_subscription.data and sub_form.validate_on_submit():
        plan_id = sub_form.subscription_plan_id.data
        ends_at = sub_form.subscription_ends_at.data

        if plan_id: # A plan is selected
            business.subscription_plan_id = plan_id
            business.subscription_status = 'active'
            if ends_at:
                # Set specific end date, converting date to datetime
                business.subscription_ends_at = datetime.combine(ends_at, datetime.min.time())
            else:
                # Calculate end date based on plan duration
                plan = SubscriptionPlan.query.get(plan_id)
                business.subscription_ends_at = datetime.utcnow() + timedelta(days=plan.duration_days)
            flash(f'Subscription updated for "{business.name}".', 'success')
        else: # No plan is selected
            business.subscription_plan_id = None
            business.subscription_status = 'expired'
            business.subscription_ends_at = None
            flash(f'Subscription removed for "{business.name}". Status set to expired.', 'warning')
        
        db.session.commit()
        return redirect(url_for('admin.edit_business', id=id))

    return render_template('admin/business_form.html', form=form, sub_form=sub_form, business=business, title="Edit Business")


@bp.route('/business/reset_stock/<int:id>', methods=['POST'])
@login_required
@admin_required
def reset_stock(id):
    business = Business.query.get_or_404(id)
    business.jar_stock = 0
    business.dispenser_stock = 0
    db.session.commit()
    flash(f'Stock for "{business.name}" has been reset to zero.', 'success')
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
            business_id=form.business_id.data,
            mobile_number=form.mobile_number.data,
            address=form.address.data
        )
        if form.role.data == 'staff':
            user.daily_wage = form.daily_wage.data
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f'User "{user.username}" has been created.')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/user_form.html', form=form, title="Add New User", user=None)

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
        user.role = form.role.data
        user.business_id = form.business_id.data

        if user.role == 'staff':
            user.daily_wage = form.daily_wage.data
        else: # Manager
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

        db.session.commit()
        flash(f'User "{user.username}" has been updated.')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/user_form.html', form=form, user=user, title="Edit User")


@bp.route('/user/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        flash('Cannot delete the admin user.')
        return redirect(url_for('admin.dashboard'))
    flash(f'User "{user.username}" has been deleted.')
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('admin.dashboard'))


# --- SaaS Management Routes ---

# Subscription Plans
@bp.route('/plans')
@login_required
@admin_required
def list_plans():
    plans = SubscriptionPlan.query.all()
    return render_template('admin/subscription_plans.html', plans=plans, title="Subscription Plans")

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
        flash('New subscription plan has been created.', 'success')
        return redirect(url_for('admin.list_plans'))
    return render_template('admin/plan_form.html', form=form, title="Add New Plan")

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
        flash('Subscription plan has been updated.', 'success')
        return redirect(url_for('admin.list_plans'))
    return render_template('admin/plan_form.html', form=form, title="Edit Plan")

@bp.route('/plans/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_plan(id):
    plan = SubscriptionPlan.query.get_or_404(id)
    if Business.query.filter_by(subscription_plan_id=id).first():
        flash('Cannot delete plan. It is currently assigned to one or more businesses.', 'danger')
    else:
        db.session.delete(plan)
        db.session.commit()
        flash(f'Plan "{plan.name}" has been deleted.', 'success')
    return redirect(url_for('admin.list_plans'))


# Coupons
@bp.route('/coupons')
@login_required
@admin_required
def list_coupons():
    coupons = Coupon.query.all()
    return render_template('admin/coupons.html', coupons=coupons, title="Manage Coupons")

@bp.route('/coupons/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_coupon():
    form = CouponForm()
    if form.validate_on_submit():
        coupon = Coupon(code=form.code.data.upper(), discount_percentage=form.discount_percentage.data,
                        is_active=form.is_active.data, expiry_date=form.expiry_date.data)
        db.session.add(coupon)
        db.session.commit()
        flash('New coupon has been created.', 'success')
        return redirect(url_for('admin.list_coupons'))
    return render_template('admin/coupon_form.html', form=form, title="Add New Coupon")

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
        coupon.expiry_date = form.expiry_date.data
        db.session.commit()
        flash('Coupon has been updated.', 'success')
        return redirect(url_for('admin.list_coupons'))
    return render_template('admin/coupon_form.html', form=form, title="Edit Coupon")

@bp.route('/coupons/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_coupon(id):
    coupon = Coupon.query.get_or_404(id)
    db.session.delete(coupon)
    db.session.commit()
    flash(f'Coupon "{coupon.code}" has been deleted.', 'success')
    return redirect(url_for('admin.list_coupons'))

@bp.route('/business/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_business(id):
    business = Business.query.get_or_404(id)
    try:
        # Due to the cascade settings in the model, deleting the business
        # will automatically delete all related employees, customers, sales, etc.
        db.session.delete(business)
        db.session.commit()
        flash(f'Business "{business.name}" and all of its associated data have been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting business: {e}', 'danger')
    return redirect(url_for('admin.dashboard'))