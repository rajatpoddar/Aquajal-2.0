# /water_supply_app/app/delivery/routes.py

from flask import (render_template, flash, redirect, url_for, request, jsonify,
                   Response, current_app, abort, make_response)
import qrcode
import io
import base64
from flask_login import login_required, current_user
from app import db
from app.delivery import bp
from app.models import Customer, DailyLog, Expense, User, JarRequest, EventBooking, Business, Invoice
from app.email import send_delivery_confirmation_email, send_event_booking_notification
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField, FloatField, DateField
from wtforms.validators import DataRequired, NumberRange, ValidationError, Optional, Email, EqualTo, Length
from sqlalchemy import or_
from datetime import date, datetime, timedelta
from app.invoices.routes import create_invoice_for_transaction

# --- Forms ---

class StaffProfileForm(FlaskForm):
    """Form for staff to edit their own profile."""
    email = StringField('Email Address', validators=[Optional(), Email()])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    submit_profile = SubmitField('Update Profile')

    def __init__(self, original_email=None, *args, **kwargs):
        super(StaffProfileForm, self).__init__(*args, **kwargs)
        self.original_email = original_email

    def validate_email(self, email):
        if email.data and email.data != self.original_email:
            # Check if email is already taken by another user or customer
            if User.query.filter(User.email == email.data).first() or \
               Customer.query.filter(Customer.email == email.data).first():
                raise ValidationError('This email address is already registered.')

class ChangePasswordForm(FlaskForm):
    """Form for users to change their password."""
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat New Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit_password = SubmitField('Change Password')


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

class ClearDuesForm(FlaskForm):
    customer_id = IntegerField('Customer ID', validators=[DataRequired()])
    submit_clear_dues = SubmitField('Clear Dues')

# --- Routes ---
@bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    search_form = SearchForm()
    expense_form = ExpenseForm()
    clear_dues_form = ClearDuesForm()

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
    
    customers_with_dues = Customer.query.filter(
        Customer.business_id == current_user.business_id,
        Customer.due_amount > 0
    ).order_by(Customer.name).all()

    return render_template(
        'delivery/dashboard.html', 
        title="Delivery Dashboard", 
        search_form=search_form,
        expense_form=expense_form,
        clear_dues_form=clear_dues_form,
        jar_requests=jar_requests,
        event_bookings_today=event_bookings_today,
        bookings_to_collect=bookings_to_collect,
        customers_with_dues=customers_with_dues,
        today=today
    )

@bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """Account page for staff members."""
    if current_user.role != 'staff':
        abort(403)

    profile_form = StaffProfileForm(original_email=current_user.email, obj=current_user)
    password_form = ChangePasswordForm()

    if profile_form.submit_profile.data and profile_form.validate_on_submit():
        current_user.email = profile_form.email.data
        current_user.mobile_number = profile_form.mobile_number.data
        db.session.commit()
        flash('Your profile has been updated.', 'success')
        return redirect(url_for('delivery.account'))
        
    if password_form.submit_password.data and password_form.validate_on_submit():
        current_user.set_password(password_form.password.data)
        db.session.commit()
        flash('Your password has been changed successfully.', 'success')
        return redirect(url_for('delivery.account'))

    return render_template('delivery/account.html', title="My Account", profile_form=profile_form, password_form=password_form)


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

        # --- EMAIL NOTIFICATION ---
        manager = User.query.filter_by(business_id=current_user.business_id, role='manager').first()
        staff_users = User.query.filter_by(business_id=current_user.business_id, role='staff').all()
        if manager and manager.email:
            staff_emails = [staff.email for staff in staff_users if staff.email]
            send_event_booking_notification(booking, manager.email, staff_emails)
        # --- END EMAIL ---
        
        if current_user.role == 'manager':
             return redirect(url_for('manager.dashboard'))
        return redirect(url_for('delivery.dashboard'))

    return render_template('delivery/book_event.html', title="Book Event for Customer", form=form)



@bp.route('/generate_upi_qr/<int:customer_id>/<float:amount>')
@login_required
def generate_upi_qr(customer_id, amount):
    # Ensure staff belongs to a business
    if not current_user.business_id:
        return jsonify({'error': 'Staff not associated with a business.'}), 403
        
    business = Business.query.get(current_user.business_id)
    customer = Customer.query.get_or_404(customer_id) # Get customer for name reference

    if not business or business.id != customer.business_id:
         abort(403) # Staff and customer must be in the same business

    if not business.upi_id:
        return jsonify({'error': 'Business UPI ID not configured.'}), 400

    if amount <= 0:
        return jsonify({'error': 'Amount must be greater than zero.'}), 400

    # UPI QR Code String Format (Standard)
    # upi://pay?pa=<UPI_ID>&pn=<Payee_Name>&am=<Amount>&cu=INR&tn=<Transaction_Note>
    payee_name = business.name.replace(' ', '%20') # URL Encode spaces
    transaction_note = f"Payment%20for%20{customer.name}".replace(' ', '%20')
    upi_string = f"upi://pay?pa={business.upi_id}&pn={payee_name}&am={amount:.2f}&cu=INR&tn={transaction_note}"

    # Generate QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(upi_string)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Save image to a byte buffer
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    # Encode as Base64 to embed in HTML
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    data_uri = f"data:image/png;base64,{img_base64}"

    return jsonify({
        'qr_image_data': data_uri,
        'upi_string': upi_string, # Optionally return the raw string
        'amount': amount,
        'upi_id': business.upi_id
    })


@bp.route('/log_delivery/<int:customer_id>', methods=['POST'])
@login_required
def log_delivery(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    user = User.query.get(current_user.id)

    # Security Check: Ensure customer belongs to the staff's business
    if customer.business_id != user.business_id:
        abort(403)

    try:
        jars_delivered = int(request.form.get('jars_delivered', customer.daily_jars))
        if jars_delivered <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        flash('Invalid number of jars.')
        return redirect(url_for('delivery.dashboard'))

    amount = jars_delivered * customer.price_per_jar
    is_due = request.form.get('is_due') # Checkbox for Cash Due
    payment_received_online = request.form.get('payment_received_online') == 'true' # Hidden field for QR code payment

    # Determine payment status and method
    payment_status = 'Due'
    invoice_status = 'Unpaid'
    payment_method = 'Due' # Default if is_due is checked

    if payment_received_online: # If paid via QR and manually confirmed
        payment_status = 'Paid'
        invoice_status = 'Paid'
        payment_method = 'Online' # <-- Set payment method
    elif not is_due: # If cash paid directly (not due)
        payment_status = 'Paid'
        invoice_status = 'Paid'
        payment_method = 'Cash' # <-- Set payment method

    log = DailyLog(
        jars_delivered=jars_delivered,
        amount_collected=amount, # Log the expected amount
        customer_id=customer.id,
        user_id=user.id,
        payment_status=payment_status,
        payment_method=payment_method # <-- Store the method
    )
    db.session.add(log)

    if user.cash_balance is None:
        user.cash_balance = 0.0

    if payment_status == 'Paid':
        # Only add to cash balance if it was paid in Cash
        if payment_method == 'Cash':
             user.cash_balance += amount
        # Clear due amount logic remains complex, handled separately
    else: # Status is 'Due'
        if customer.due_amount is None:
            customer.due_amount = 0.0
        customer.due_amount += amount

    db.session.commit()

    invoice_items = [{
        'description': f"Supply of {jars_delivered} water jar(s)",
        'quantity': jars_delivered,
        'unit_price': customer.price_per_jar,
        'total': amount
    }]
    # Pass payment_method info potentially to invoice description or notes if needed? (Optional Enhancement)
    invoice = create_invoice_for_transaction(customer, customer.business, invoice_items, issue_date=log.timestamp.date(), status=invoice_status)

    if invoice and payment_status == 'Paid': # Send confirmation only if paid
        send_delivery_confirmation_email(customer, customer.business, jars_delivered, amount, payment_status)

    flash(f'Successfully logged delivery of {jars_delivered} jar(s) to {customer.name}. Status: {payment_status} ({payment_method}).') # <-- Added method to flash
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

@bp.route('/clear_dues', methods=['POST'])
@login_required
def clear_dues():
    form = ClearDuesForm()
    if form.validate_on_submit():
        customer = Customer.query.get_or_404(form.customer_id.data)
        if customer.business_id != current_user.business_id:
            abort(403)

        amount_cleared = customer.due_amount
        customer.due_amount = 0.0

        # Update staff's cash balance
        staff_member = User.query.get(current_user.id)
        if staff_member.cash_balance is None:
            staff_member.cash_balance = 0.0
        staff_member.cash_balance += amount_cleared

        # Mark 'Due' logs as 'Paid'
        DailyLog.query.filter_by(customer_id=customer.id, payment_status='Due').update({'payment_status': 'Paid'})
        
        # Mark all 'Unpaid' invoices as 'Paid' for this customer
        Invoice.query.filter_by(customer_id=customer.id, status='Unpaid').update({'status': 'Paid'})
        
        db.session.commit()
        flash(f'Dues of ₹{amount_cleared:.2f} for {customer.name} have been cleared and added to your cash balance.', 'success')
    else:
        flash('Invalid request to clear dues.', 'danger')

    return redirect(url_for('delivery.dashboard'))

# --- API ROUTE FOR LIVE SEARCH ---
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
        {'id': c.id, 'name': c.name, 'mobile_number': c.mobile_number, 'area': c.area, 'village': c.village,
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
    
    amount = jar_request.quantity * jar_request.customer.price_per_jar
    
    log = DailyLog(
        jars_delivered=jar_request.quantity,
        amount_collected=amount,
        customer_id=jar_request.customer_id,
        user_id=current_user.id,
        payment_status='Paid', # Assume requested jars are paid on delivery
        origin='customer_request' # Set the origin
    )
    db.session.add(log)
    
    user = User.query.get(current_user.id)
    if user.cash_balance is None: user.cash_balance = 0.0
    user.cash_balance += log.amount_collected
    
    jar_request.status = 'Delivered'
    jar_request.delivered_by_id = current_user.id
    jar_request.delivery_timestamp = datetime.utcnow()
    
    db.session.commit()
    
    # --- AUTOMATIC INVOICE GENERATION FOR REQUEST ---
    invoice_items = [{
        'description': f"Supply of {log.jars_delivered} requested water jar(s)",
        'quantity': log.jars_delivered,
        'unit_price': jar_request.customer.price_per_jar,
        'total': amount
    }]
    create_invoice_for_transaction(jar_request.customer, jar_request.customer.business, invoice_items, issue_date=log.timestamp.date(), status='Paid')
    # --- END ---

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
        if not (0 <= dispensers_returned <= (booking.dispensers_booked or 0)):
            raise ValueError("Invalid number of dispensers returned.")
    except (TypeError, ValueError) as e:
        flash(str(e), 'danger')
        return redirect(url_for('delivery.dashboard'))

    business = Business.query.get(current_user.business_id)
    staff_member = User.query.get(current_user.id)

    business.jar_stock += jars_returned
    business.dispenser_stock += dispensers_returned

    missing_jars = booking.quantity - jars_returned
    missing_dispensers = (booking.dispensers_booked or 0) - dispensers_returned
    
    amount_for_missing_jars = 0
    amount_for_missing_dispensers = 0

    if missing_jars > 0:
        amount_for_missing_jars = missing_jars * business.new_jar_price
    if missing_dispensers > 0:
        amount_for_missing_dispensers = missing_dispensers * business.new_dispenser_price
    
    total_amount_for_missing_items = amount_for_missing_jars + amount_for_missing_dispensers
    
    if total_amount_for_missing_items > 0:
        flash(f"Please collect an additional ₹{total_amount_for_missing_items:.2f} for missing items.", "warning")
        if staff_member.cash_balance is None: staff_member.cash_balance = 0.0
        staff_member.cash_balance += total_amount_for_missing_items

    booking.status = 'Completed'
    booking.jars_returned = jars_returned
    booking.dispensers_returned = dispensers_returned
    booking.final_amount = (booking.amount or 0) + total_amount_for_missing_items
    booking.collection_timestamp = datetime.utcnow()
    booking.collected_by_id = current_user.id

    # --- DETAILED INVOICE GENERATION ---
    invoice_items = [{
        'description': f"Event Booking ({booking.quantity} Jars, {booking.dispensers_booked or 0} Dispensers)",
        'quantity': 1,
        'unit_price': booking.amount or 0,
        'total': booking.amount or 0
    }]
    if missing_jars > 0:
        invoice_items.append({
            'description': f"Charge for {missing_jars} missing/lost jar(s)",
            'quantity': missing_jars,
            'unit_price': business.new_jar_price,
            'total': amount_for_missing_jars
        })
    if missing_dispensers > 0:
        invoice_items.append({
            'description': f"Charge for {missing_dispensers} missing/lost dispenser(s)",
            'quantity': missing_dispensers,
            'unit_price': business.new_dispenser_price,
            'total': amount_for_missing_dispensers
        })

    create_invoice_for_transaction(booking.customer, booking.customer.business, invoice_items, issue_date=booking.collection_timestamp.date(), status='Paid')
    # --- END ---
    
    db.session.commit()
    flash(f"Collection from {booking.customer.name} completed. Stock and balance updated.", "success")
    return redirect(url_for('delivery.dashboard'))