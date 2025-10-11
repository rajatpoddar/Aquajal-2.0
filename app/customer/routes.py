# /water_supply_app/app/customer/routes.py
from flask import render_template, flash, redirect, url_for, request
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.customer import bp
from app.models import Customer, DailyLog, JarRequest, EventBooking
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, DateField
from wtforms.validators import DataRequired, NumberRange, ValidationError
from datetime import date, timedelta

# --- Forms ---
class JarRequestForm(FlaskForm):
    quantity = IntegerField('Number of Jars', default=1, validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Request Jars')

class EventBookingForm(FlaskForm):
    quantity = IntegerField('Number of Jars for Event', validators=[DataRequired(), NumberRange(min=1)])
    event_date = DateField('Date of Event', validators=[DataRequired()])
    submit = SubmitField('Book for Event')

    def validate_event_date(self, event_date):
        if event_date.data < date.today() + timedelta(days=1):
            raise ValidationError('Event booking must be for tomorrow or a future date.')
# --- Routes ---
@bp.route('/dashboard')
@login_required
def dashboard():
    if not hasattr(current_user, 'role') or current_user.role != 'customer':
        return redirect(url_for('index'))
    jar_request_form = JarRequestForm()
    event_booking_form = EventBookingForm()
    reports = DailyLog.query.filter_by(customer_id=current_user.id).order_by(DailyLog.timestamp.desc()).limit(10).all()
    requests = JarRequest.query.filter_by(customer_id=current_user.id).order_by(JarRequest.request_timestamp.desc()).limit(5).all()
    bookings = EventBooking.query.filter_by(customer_id=current_user.id).order_by(EventBooking.request_timestamp.desc()).limit(5).all()
    return render_template('customer/dashboard.html', title='My Dashboard', reports=reports, requests=requests, bookings=bookings, jar_form=jar_request_form, event_form=event_booking_form)

@bp.route('/request_jar', methods=['POST'])
@login_required
def request_jar():
    form = JarRequestForm()
    if form.validate_on_submit():
        new_request = JarRequest(quantity=form.quantity.data, customer_id=current_user.id)
        db.session.add(new_request)
        db.session.commit()
        flash(f'Your request for {form.quantity.data} jar(s) has been sent!')
    else:
        flash('There was an error with your request.')
    return redirect(url_for('customer.dashboard'))

@bp.route('/book_event', methods=['POST'])
@login_required
def book_event():
    form = EventBookingForm()
    if form.validate_on_submit():
        booking = EventBooking(quantity=form.quantity.data, event_date=form.event_date.data, customer_id=current_user.id)
        db.session.add(booking)
        db.session.commit()
        flash(f'Your event booking for {form.quantity.data} jars on {form.event_date.data} has been submitted for confirmation.')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", 'danger')
    return redirect(url_for('customer.dashboard'))