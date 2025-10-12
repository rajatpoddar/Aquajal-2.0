# /water_supply_app/app/delivery/routes.py

from flask import render_template, flash, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.delivery import bp
from app.models import Customer, DailyLog, Expense, User, JarRequest, EventBooking, Business
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, FloatField, DateField
from wtforms.validators import DataRequired, NumberRange, ValidationError, Optional
from sqlalchemy import or_
from datetime import date, datetime, timedelta

# --- Forms ---
class EventBookingByStaffForm(FlaskForm):
    customer_id = IntegerField('Customer', validators=[DataRequired()])
    quantity = IntegerField('Number of Jars', validators=[DataRequired(), NumberRange(min=0)])
    dispensers_booked = IntegerField('Number of Dispensers', validators=[Optional(), NumberRange(min=0)], default=0)
    event_date = DateField('Date of Event', validators=[DataRequired()])
    submit = SubmitField('Create Booking')

    def validate_event_date(self, event_date):
        if event_date.data < date.today():
            raise ValidationError('Event booking must be for today or a future date.')

    def validate(self, **kwargs):
        if not super().validate(**kwargs):
            return False
        # Use .data to access the value, defaulting to 0 if None
        jars = self.quantity.data or 0
        dispensers = self.dispensers_booked.data or 0
        if jars <= 0 and dispensers <= 0:
            self.quantity.errors.append('You must book at least one jar or one dispenser.')
            return False
        return True


class SearchForm(FlaskForm):
    search_term = StringField('Search by Name or Mobile')
class ExpenseForm(FlaskForm):
    amount = FloatField('Amount (₹)', validators=[DataRequired()])
    description = StringField('Description (e.g., Fuel)', validators=[DataRequired()], default='Fuel')
    submit_expense = SubmitField('Add Expense')

# --- Routes ---
@bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    search_form = SearchForm()
    expense_form = ExpenseForm()

    today = date.today()
    
    jar_requests = db.session.query(JarRequest).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        JarRequest.status == 'Pending'
    ).order_by(JarRequest.request_timestamp).all()
    
    event_bookings_today = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        EventBooking.status == 'Confirmed',
        EventBooking.event_date == today
    ).order_by(EventBooking.request_timestamp).all()

    bookings_to_collect = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        EventBooking.status == 'Delivered'
    ).order_by(EventBooking.delivery_timestamp).all()

    return render_template(
        'delivery/dashboard.html', 
        title="Delivery Dashboard", 
        search_form=search_form,
        expense_form=expense_form,
        jar_requests=jar_requests,
        event_bookings_today=event_bookings_today,
        bookings_to_collect=bookings_to_collect,
        today=today
    )

@bp.route('/book_event', methods=['GET', 'POST'])
@login_required
def book_event():
    form = EventBookingByStaffForm()

    if form.validate_on_submit():
        customer = Customer.query.filter_by(id=form.customer_id.data, business_id=current_user.business_id).first()
        if not customer:
            flash('Invalid customer selected.', 'danger')
            return render_template('delivery/book_event.html', title="Book Event for Customer", form=form)

        booking = EventBooking(
            customer_id=form.customer_id.data,
            quantity=form.quantity.data,
            dispensers_booked=form.dispensers_booked.data,
            event_date=form.event_date.data
        )
        db.session.add(booking)
        db.session.commit()
        
        flash(f'Event booking created successfully for {customer.name}. The manager must now confirm it.', 'success')
        
        if current_user.role == 'manager':
             return redirect(url_for('manager.dashboard'))
        return redirect(url_for('delivery.dashboard'))

    return render_template('delivery/book_event.html', title="Book Event for Customer", form=form)



@bp.route('/log_delivery/<int:customer_id>', methods=['POST'])
@login_required
def log_delivery(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    user = User.query.get(current_user.id)
    
    try:
        jars_delivered = int(request.form.get('jars_delivered', customer.daily_jars))
        if jars_delivered <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        flash('Invalid number of jars.')
        return redirect(url_for('delivery.dashboard'))

    amount = jars_delivered * customer.price_per_jar
    
    log = DailyLog(
        jars_delivered=jars_delivered,
        amount_collected=amount,
        customer_id=customer.id,
        user_id=user.id
    )
    db.session.add(log)
    
    if user.cash_balance is None:
        user.cash_balance = 0.0
    
    user.cash_balance += amount
    
    db.session.commit()
    flash(f'Successfully delivered {jars_delivered} jar(s) to {customer.name}. Collected ₹{amount:.2f}.')
    return redirect(url_for('delivery.dashboard'))

@bp.route('/add_expense', methods=['POST'])
@login_required
def add_expense():
    expense_form = ExpenseForm()
    if expense_form.validate_on_submit():
        user = User.query.get(current_user.id)
        amount = expense_form.amount.data
        description = expense_form.description.data

        expense = Expense(
            amount=amount,
            description=description,
            user_id=user.id
        )
        db.session.add(expense)

        if user.cash_balance is None:
            user.cash_balance = 0.0

        user.cash_balance -= amount

        db.session.commit()
        flash(f'Expense of ₹{amount:.2f} for "{description}" recorded.')
    else:
        flash('Invalid expense data.')
        
    return redirect(url_for('delivery.dashboard'))

# --- API ROUTE FOR LIVE SEARCH ---
@bp.route('/api/search_customers')
@login_required
def search_customers():
    query = request.args.get('q', '', type=str)
    if not query:
        return jsonify([])

    term = f"%{query}%"
    customers = Customer.query.filter(
        Customer.business_id == current_user.business_id,
        or_(
            Customer.name.ilike(term),
            Customer.mobile_number.ilike(term)
        )
    ).limit(10).all()

    results = [
        {'id': c.id, 'name': c.name, 'area': c.area, 'village': c.village,
         'daily_jars': c.daily_jars, 'price_per_jar': c.price_per_jar}
        for c in customers
    ]
    return jsonify(results)

@bp.route('/confirm_jar_request/<int:request_id>')
@login_required
def confirm_jar_request(request_id):
    jar_request = db.session.query(JarRequest).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        JarRequest.id == request_id
    ).first_or_404()
    
    log = DailyLog(
        jars_delivered=jar_request.quantity,
        amount_collected=jar_request.quantity * jar_request.customer.price_per_jar,
        customer_id=jar_request.customer_id,
        user_id=current_user.id
    )
    db.session.add(log)
    
    user = User.query.get(current_user.id)
    if user.cash_balance is None: user.cash_balance = 0.0
    user.cash_balance += log.amount_collected
    
    jar_request.status = 'Delivered'
    jar_request.delivered_by_id = current_user.id
    jar_request.delivery_timestamp = datetime.utcnow()
    
    db.session.commit()
    flash(f'Delivery to {jar_request.customer.name} confirmed.')
    return redirect(url_for('delivery.dashboard'))

@bp.route('/confirm_event_delivery/<int:booking_id>')
@login_required
def confirm_event_delivery(booking_id):
    booking = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        EventBooking.id == booking_id
    ).first_or_404()

    if booking.paid_to_manager:
        flash('Delivery confirmed. Payment was handled by the manager.')
    else:
        staff_member = User.query.get(current_user.id)
        if staff_member.cash_balance is None: staff_member.cash_balance = 0.0
        staff_member.cash_balance += booking.amount
        flash(f'Delivery confirmed. ₹{booking.amount:.2f} collected and added to your balance.')
    
    booking.status = 'Delivered'
    booking.delivered_by_id = current_user.id
    booking.delivery_timestamp = datetime.utcnow()
    db.session.commit()
    
    return redirect(url_for('delivery.dashboard'))

@bp.route('/collect_event_jars/<int:booking_id>', methods=['POST'])
@login_required
def collect_event_jars(booking_id):
    booking = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        EventBooking.id == booking_id,
        EventBooking.status == 'Delivered'
    ).first_or_404()

    try:
        jars_returned = int(request.form.get('jars_returned'))
        dispensers_returned = int(request.form.get('dispensers_returned'))
        if not (0 <= jars_returned <= booking.quantity):
            raise ValueError("Invalid number of jars returned.")
        if not (0 <= dispensers_returned <= booking.dispensers_booked):
            raise ValueError("Invalid number of dispensers returned.")
    except (TypeError, ValueError) as e:
        flash(str(e), 'danger')
        return redirect(url_for('delivery.dashboard'))

    business = Business.query.get(current_user.business_id)
    staff_member = User.query.get(current_user.id)

    business.jar_stock += jars_returned
    business.dispenser_stock += dispensers_returned

    missing_jars = booking.quantity - jars_returned
    missing_dispensers = booking.dispensers_booked - dispensers_returned
    amount_to_collect = 0

    if missing_jars > 0:
        amount_to_collect += missing_jars * business.new_jar_price
    if missing_dispensers > 0:
        amount_to_collect += missing_dispensers * business.new_dispenser_price
    
    if amount_to_collect > 0:
        flash(f"Please collect an additional ₹{amount_to_collect:.2f} for missing items.", "warning")

    if amount_to_collect > 0:
        if staff_member.cash_balance is None: staff_member.cash_balance = 0.0
        staff_member.cash_balance += amount_to_collect

    booking.status = 'Completed'
    booking.jars_returned = jars_returned
    booking.dispensers_returned = dispensers_returned
    booking.final_amount = (booking.amount or 0) + amount_to_collect
    booking.collection_timestamp = datetime.utcnow()
    booking.collected_by_id = current_user.id
    
    db.session.commit()
    flash(f"Collection from {booking.customer.name} completed. Stock and balance updated.", "success")
    return redirect(url_for('delivery.dashboard'))