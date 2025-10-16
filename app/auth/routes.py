from flask import render_template, flash, redirect, url_for, request
from flask_login import login_user, logout_user, current_user
from app import db
from app.auth import bp
from app.models import User, Customer
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired
from sqlalchemy import or_, func
from flask_babel import _, lazy_gettext as _l

class LoginForm(FlaskForm):
    username = StringField(_l('Username, Email, or Mobile Number'), validators=[DataRequired()])
    password = PasswordField(_l('Password'), validators=[DataRequired()])
    remember_me = BooleanField(_l('Remember Me'))
    submit = SubmitField(_l('Sign In'))

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if hasattr(current_user, 'role'): # Check if the user is an employee
            if current_user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'manager':
                return redirect(url_for('manager.dashboard'))
            elif current_user.role == 'supplier':
                return redirect(url_for('supplier.dashboard'))
            elif current_user.role == 'staff':
                return redirect(url_for('delivery.dashboard'))
        elif isinstance(current_user, Customer): # Check if the user is a customer
             return redirect(url_for('customer.dashboard'))
        else:
            return redirect(url_for('public.index'))

    form = LoginForm()
    if form.validate_on_submit():
        login_identifier = form.username.data
        
        user_to_login = None
        
        # First, try to find an employee (User) by username, email or mobile
        user = User.query.filter(
            or_(func.lower(User.username) == login_identifier.lower(), 
                func.lower(User.email) == login_identifier.lower(), 
                User.mobile_number == login_identifier)
        ).first()

        if user and user.check_password(form.password.data):
            user_to_login = user

        # If no employee was found, try to find a Customer
        if not user_to_login:
            customer = Customer.query.filter(
                or_(func.lower(Customer.username) == login_identifier.lower(), 
                    func.lower(Customer.email) == login_identifier.lower(), 
                    Customer.mobile_number == login_identifier)
            ).first()
            if customer and customer.check_password(form.password.data):
                user_to_login = customer
        
        if user_to_login:
            login_user(user_to_login, remember=form.remember_me.data)
            next_page = request.args.get('next')
            if not next_page:
                if hasattr(user_to_login, 'role'):
                    if user_to_login.role == 'admin':
                        next_page = url_for('admin.dashboard')
                    elif user_to_login.role == 'manager':
                        next_page = url_for('manager.dashboard')
                    elif user_to_login.role == 'supplier':
                        next_page = url_for('supplier.dashboard')
                    elif user_to_login.role == 'staff':
                        next_page = url_for('delivery.dashboard')
                elif isinstance(user_to_login, Customer):
                    next_page = url_for('customer.dashboard')
                else:
                    next_page = url_for('public.index')
            return redirect(next_page)
        else:
            flash(_('Invalid username/mobile or password'))
            return redirect(url_for('auth.login'))
        
    return render_template('auth/login.html', title=_('Sign In'), form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('public.index'))
