# /water_supply_app/app/auth/routes.py

from flask import render_template, flash, redirect, url_for, request
from flask_login import login_user, logout_user, current_user
from app import db
from app.auth import bp
from app.models import User, Customer # Import both models
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired
from sqlalchemy import or_ # Import 'or_' for combined queries

class LoginForm(FlaskForm):
    username = StringField('Username or Mobile Number', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        login_identifier = form.username.data
        
        # --- UNIFIED LOGIN LOGIC ---
        user_to_login = None
        
        # First, try to find an employee (User) by username or mobile
        user = User.query.filter(
            or_(User.username == login_identifier, User.mobile_number == login_identifier)
        ).first()
        if user and user.check_password(form.password.data):
            user_to_login = user

        # If no employee was found, try to find a Customer by username or mobile
        if not user_to_login:
            customer = Customer.query.filter(
                or_(Customer.username == login_identifier, Customer.mobile_number == login_identifier)
            ).first()
            if customer and customer.check_password(form.password.data):
                user_to_login = customer
        
        # If we found a user or customer, log them in
        if user_to_login:
            login_user(user_to_login, remember=form.remember_me.data)
            return redirect(url_for('index'))
        else:
            flash('Invalid username/mobile or password')
            return redirect(url_for('auth.login'))
        
    return render_template('auth/login.html', title='Sign In', form=form)

@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))