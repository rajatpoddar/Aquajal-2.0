# /water_supply_app/app/customer/routes.py
from flask import render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required
from app import db
from app.customer import bp
from app.models import Customer, DailyLog, JarRequest, EventBooking, Invoice
from flask_wtf import FlaskForm
from wtforms import IntegerField, DateField, SubmitField
from wtforms.validators import DataRequired, NumberRange, ValidationError
from datetime import date, timedelta
from math import ceil

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
    jar_request_form = JarRequestForm()
    event_booking_form = EventBookingForm()
    due_amount = current_user.due_amount or 0.0
    
    # --- Pagination for Invoices ---
    page_invoices = request.args.get('page_invoices', 1, type=int)
    invoices_pagination = current_user.invoices.order_by(Invoice.issue_date.desc()).paginate(
        page=page_invoices, per_page=5, error_out=False
    )

    # --- Create and Paginate Unified Activity Log ---
    logs = DailyLog.query.filter_by(customer_id=current_user.id).all()
    bookings = EventBooking.query.filter_by(customer_id=current_user.id).all()

    activity_log = []
    for log in logs:
        activity_log.append({'type': 'Requested Delivery' if log.origin == 'customer_request' else 'Regular Delivery', 'item': log, 'date': log.timestamp})
    for booking in bookings:
        activity_log.append({'type': 'Booking Delivery', 'item': booking, 'date': booking.request_timestamp})

    activity_log.sort(key=lambda x: x['date'], reverse=True)
    
    page_activity = request.args.get('page_activity', 1, type=int)
    per_page_activity = 5
    start = (page_activity - 1) * per_page_activity
    end = start + per_page_activity
    paginated_activity = activity_log[start:end]
    total_activity_pages = ceil(len(activity_log) / per_page_activity)

    return render_template(
        'customer/dashboard.html', 
        title='My Dashboard', 
        jar_form=jar_request_form, 
        event_form=event_booking_form,
        invoices_pagination=invoices_pagination, 
        due_amount=due_amount,
        activity_log=paginated_activity,
        page_activity=page_activity,
        total_activity_pages=total_activity_pages
    )


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