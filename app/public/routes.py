from flask import render_template, flash, redirect, url_for, request, session, send_from_directory, current_app
from flask_login import login_user, current_user
from app import db
from app.public import bp
from app.models import User, Business, Customer, SubscriptionPlan
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, Email, ValidationError, Regexp
import random
import string
from app.email import send_password_reset_email, send_registration_email
from flask import current_app

class RegistrationForm(FlaskForm):
    owner_name = StringField('Your Name', validators=[DataRequired()])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64), Regexp('^[a-z0-9]+$', message='Username must be lowercase letters and numbers only.')])
    plant_name = StringField('Plant Name', validators=[DataRequired()])
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), Length(min=10, max=15)])
    address = StringField('Plant Address', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Start Your Free Trial')

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first() or Customer.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken. Please choose a different one.')

    def validate_plant_name(self, plant_name):
        business = Business.query.filter_by(name=plant_name.data).first()
        if business:
            raise ValidationError('This plant name is already registered. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('This email address is already registered.')

    def validate_mobile_number(self, mobile_number):
        user = User.query.filter_by(mobile_number=mobile_number.data).first()
        if user:
            raise ValidationError('This mobile number is already registered.')

class ResetPasswordRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField(
        'Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Request Password Reset')


@bp.route('/')
@bp.route('/index')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.duration_days).all()
    return render_template('public/index.html', title='Welcome', plans=plans)


@bp.route('/about')
def about():
    return render_template('public/about.html', title='About Us')


@bp.route('/contact')
def contact():
    return render_template('public/contact.html', title='Contact Us')


@bp.route('/how-to-use')
def how_to_use():
    return render_template('public/how_to_use.html', title='How to Use')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        # Create a new business
        business = Business(
            name=form.plant_name.data,
            owner_name=form.owner_name.data,
            email=form.email.data,
            location=form.address.data
        )
        db.session.add(business)
        db.session.commit()
        
        # Create a new user with the manager role
        user = User(
            username=form.username.data,
            email=form.email.data,
            mobile_number=form.mobile_number.data,
            role='manager',
            business_id=business.id
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        # Send the welcome email
        send_registration_email(user)

        # Log in the new user automatically
        login_user(user)
        flash(f'Congratulations {form.owner_name.data}, your business "{form.plant_name.data}" is now registered! A welcome email has been sent to you.', 'success')
        return redirect(url_for('manager.dashboard'))
    return render_template('public/register.html', title='Register', form=form)

@bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('Check your email for the instructions to reset your password')
        return redirect(url_for('auth.login'))
    return render_template('public/reset_password_request.html',
                           title='Reset Password', form=form)

@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('public.index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.')
        return redirect(url_for('auth.login'))
    return render_template('public/reset_password.html', form=form)

@bp.route('/offline')
def offline():
    return render_template('public/offline.html', title='Offline')

@bp.route('/language/<language>')
def set_language(language=None):
    if language in current_app.config['LANGUAGES']:
        session['language'] = language
    return redirect(request.referrer or url_for('public.index'))

# --- NEW ROUTES FOR SITEMAP AND ROBOTS.TXT ---

@bp.route('/sitemap.xml')
def sitemap():
    """Serves the sitemap.xml file from the static directory."""
    return send_from_directory(current_app.static_folder, 'sitemap.xml')

@bp.route('/robots.txt')
def robots_txt():
    """Serves the robots.txt file from the static directory."""
    return send_from_directory(current_app.static_folder, 'robots.txt')