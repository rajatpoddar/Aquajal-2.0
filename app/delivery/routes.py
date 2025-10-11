# /water_supply_app/app/delivery/routes.py

from flask import render_template, flash, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.delivery import bp
from app.models import Customer, DailyLog, Expense, User, JarRequest, EventBooking
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, FloatField
from wtforms.validators import DataRequired
from sqlalchemy import or_
from datetime import date, datetime

# --- Forms (unchanged) ---
class SearchForm(FlaskForm):
    search_term = StringField('Search by Name or Mobile')
class ExpenseForm(FlaskForm):
    amount = FloatField('Amount (₹)', validators=[DataRequired()])
    description = StringField('Description (e.g., Fuel)', validators=[DataRequired()], default='Fuel')
    submit_expense = SubmitField('Add Expense')

# --- Routes ---
# --- THE FIX IS ON THE NEXT LINE ---
@bp.route('/dashboard', methods=['GET']) # Changed from '/' to '/dashboard'
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

    return render_template(
        'delivery/dashboard.html', 
        title="Delivery Dashboard", 
        search_form=search_form,
        expense_form=expense_form,
        jar_requests=jar_requests,
        event_bookings_today=event_bookings_today,
        today=today
    )

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

# --- NEW API ROUTE FOR LIVE SEARCH ---
@bp.route('/api/search_customers')
@login_required
def search_customers():
    query = request.args.get('q', '', type=str)
    if not query:
        return jsonify([])

    term = f"%{query}%"
    customers = Customer.query.filter(or_(
        Customer.name.ilike(term),
        Customer.mobile_number.ilike(term)
    )).limit(10).all()

    # Convert customer objects to a list of dictionaries
    results = [
        {
            'id': c.id,
            'name': c.name,
            'area': c.area,
            'village': c.village,
            'daily_jars': c.daily_jars,
            'price_per_jar': c.price_per_jar
        }
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
    
    # Create a DailyLog entry for this delivery
    log = DailyLog(
        jars_delivered=jar_request.quantity,
        amount_collected=jar_request.quantity * jar_request.customer.price_per_jar,
        customer_id=jar_request.customer_id,
        user_id=current_user.id
    )
    db.session.add(log)
    
    # Update user's cash balance
    user = User.query.get(current_user.id)
    if user.cash_balance is None: user.cash_balance = 0.0
    user.cash_balance += log.amount_collected
    
    # Update request status
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
        # Payment was already handled by the manager
        flash('Delivery confirmed. Payment was handled by the manager.')
    else:
        # Staff collects payment, update their balance
        staff_member = User.query.get(current_user.id)
        if staff_member.cash_balance is None: staff_member.cash_balance = 0.0
        staff_member.cash_balance += booking.amount
        flash(f'Delivery confirmed. ₹{booking.amount:.2f} collected and added to your balance.')
    
    booking.status = 'Delivered'
    booking.delivered_by_id = current_user.id
    booking.delivery_timestamp = datetime.utcnow()
    db.session.commit()
    
    return redirect(url_for('delivery.dashboard'))