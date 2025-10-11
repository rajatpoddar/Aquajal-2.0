# /water_supply_app/app/admin/routes.py

from flask import render_template, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from app import db
from app.admin import bp
from app.models import User, Business
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, SelectField
from wtforms.validators import DataRequired, Length, EqualTo, Optional, ValidationError
from functools import wraps

# --- Custom Decorator for Admin Access ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# --- Forms ---
class BusinessForm(FlaskForm):
    name = StringField('Business Name (e.g., Plant Location)', validators=[DataRequired()])
    new_jar_price = FloatField('Default New Jar Price (₹)', default=150.0, validators=[DataRequired()])
    new_dispenser_price = FloatField('Default New Dispenser Price (₹)', default=1500.0, validators=[DataRequired()])
    submit = SubmitField('Save Business')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    role = SelectField('Role', choices=[('staff', 'Staff'), ('manager', 'Manager')], validators=[DataRequired()])
    business_id = SelectField('Assign to Business', coerce=int, validators=[DataRequired()])
    daily_wage = FloatField('Daily Wage (₹)', validators=[Optional()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
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
    role = SelectField('Role', choices=[('staff', 'Staff'), ('manager', 'Manager')], validators=[DataRequired()])
    business_id = SelectField('Assign to Business', coerce=int, validators=[DataRequired()])
    daily_wage = FloatField('Daily Wage (₹)', validators=[Optional()])
    submit = SubmitField('Update User')

    def __init__(self, original_username, *args, **kwargs):
        super(EditUserForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.business_id.choices = [(b.id, b.name) for b in Business.query.order_by('name').all()]

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')


# --- Routes ---
@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    businesses = Business.query.order_by(Business.name).all()
    users = User.query.filter(User.role != 'admin').order_by(User.business_id, User.username).all()
    return render_template('admin/dashboard.html', businesses=businesses, users=users, title="Admin Dashboard")

# --- Business Management ---
@bp.route('/business/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_business():
    form = BusinessForm()
    if form.validate_on_submit():
        business = Business(name=form.name.data, new_jar_price=form.new_jar_price.data, new_dispenser_price=form.new_dispenser_price.data)
        db.session.add(business)
        db.session.commit()
        flash(f'Business "{business.name}" created successfully.')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/business_form.html', form=form, title="Create New Business")

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
            daily_wage=form.daily_wage.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f'User "{user.username}" has been created.')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/user_form.html', form=form, title="Add New User")

@bp.route('/user/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(id):
    user = User.query.get_or_404(id)
    form = EditUserForm(original_username=user.username, obj=user)
    if form.validate_on_submit():
        user.username = form.username.data
        user.role = form.role.data
        user.business_id = form.business_id.data
        user.daily_wage = form.daily_wage.data
        db.session.commit()
        flash(f'User "{user.username}" has been updated.')
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/user_form.html', form=form, title="Edit User")

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