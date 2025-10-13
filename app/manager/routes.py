# /water_supply_app/app/manager/routes.py

from flask import render_template, flash, redirect, url_for, request, abort, current_app
from flask_login import login_required, current_user
from app import db
from app.manager import bp
from app.models import User, DailyLog, Expense, CashHandover, ProductSale, Customer, Business, JarRequest, EventBooking, Invoice, InvoiceItem
from functools import wraps
from datetime import date, datetime, timedelta
from sqlalchemy import func, cast, Date
from zoneinfo import ZoneInfo
import os
import calendar
from werkzeug.utils import secure_filename

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, FloatField, SubmitField, IntegerField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length, ValidationError, EqualTo

# Import the form from the delivery blueprint
from app.delivery.routes import EventBookingByStaffForm

# --- Forms ---
class AddStaffForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    address = TextAreaField('Address', validators=[Optional(), Length(max=200)])
    daily_wage = FloatField('Daily Wage (₹)', validators=[Optional()])
    id_proof = FileField('ID Proof Image (JPG, PNG)', validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])
    submit = SubmitField('Create Staff Member')

    def validate_username(self, username):
        # Check if username exists in either User or Customer table to prevent login conflicts
        if User.query.filter_by(username=username.data).first() or Customer.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken. Please choose a different one.')

class ChangePasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat New Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit_password = SubmitField('Change Password')

class BusinessSettingsForm(FlaskForm):
    new_jar_price = FloatField('New Jar Price (₹)', validators=[DataRequired()])
    new_dispenser_price = FloatField('New Dispenser Price (₹)', validators=[DataRequired()])
    full_day_jar_count = IntegerField('Jars for Full Day Wage', validators=[DataRequired()])
    half_day_jar_count = IntegerField('Jars for Half Day Wage', validators=[DataRequired()])
    submit = SubmitField('Save Settings')

class StockForm(FlaskForm):
    jars_added = IntegerField('New Jars to Add', validators=[Optional()])
    dispensers_added = IntegerField('New Dispensers to Add', validators=[Optional()])
    submit = SubmitField('Update Stock')

class EditStaffByManagerForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    password = PasswordField('New Password (leave blank to keep current)', validators=[Optional(), Length(min=6)])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    address = StringField('Address', validators=[Optional(), Length(max=200)])
    daily_wage = FloatField('Daily Wage (₹)', validators=[Optional()])
    id_proof = FileField('ID Proof Image (JPG, PNG)', validators=[
        Optional(), 
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])
    submit = SubmitField('Update Staff')
    
    def __init__(self, original_username, *args, **kwargs):
        super(EditStaffByManagerForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')
            
class EventConfirmationForm(FlaskForm):
    amount = FloatField('Total Amount (₹)', validators=[DataRequired()])
    paid_to_manager = BooleanField('Payment received directly by you (Manager)?')
    submit = SubmitField('Confirm Booking')


# --- Custom Decorators ---
def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['admin', 'manager']:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    """
    Ensures the manager's business has an active subscription or is in a trial period.
    This decorator should be placed AFTER @login_required and @manager_required.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Admins are not subject to subscription checks
        if current_user.role == 'admin':
            return f(*args, **kwargs)

        business = Business.query.get(current_user.business_id)
        if not business:
            flash("You are not associated with a business.", "danger")
            return redirect(url_for('auth.logout'))

        is_active = False
        now = datetime.utcnow()

        # Check 1: Is there an active subscription?
        if business.subscription_status == 'active' and business.subscription_ends_at and business.subscription_ends_at > now:
            is_active = True
        # Check 2: Are they still in the trial period?
        elif business.subscription_status == 'trial' and business.trial_ends_at and business.trial_ends_at > now:
            is_active = True

        if not is_active:
            # If trial has ended and status hasn't been updated, update it now
            if business.subscription_status == 'trial':
                business.subscription_status = 'expired'
                db.session.commit()
            # Redirect to a page that tells them to subscribe
            return redirect(url_for('billing.expired'))
            
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---
@bp.route('/dashboard')
@login_required
@manager_required
@subscription_required
def dashboard():
    staff_members = []
    total_staff_balance = 0.0
    pending_bookings = []

    if not current_user.business_id:
        flash("You are not assigned to a business. Please contact the administrator.")
    else:
        staff_members = User.query.filter_by(role='staff', business_id=current_user.business_id).order_by(User.username).all()
        total_staff_balance = sum(staff.cash_balance for staff in staff_members if staff.cash_balance)
        pending_bookings = db.session.query(EventBooking).join(Customer).filter(
            Customer.business_id == current_user.business_id,
            EventBooking.status == 'Pending'
        ).order_by(EventBooking.event_date).all()

    return render_template(
        'manager/dashboard.html',
        title="Manager Dashboard",
        staff_members=staff_members,
        total_staff_balance=total_staff_balance,
        pending_bookings=pending_bookings
    )


@bp.route('/receive_cash/<int:staff_id>', methods=['POST'])
@login_required
@manager_required
@subscription_required
def receive_cash(staff_id):
    staff = User.query.get_or_404(staff_id)
    if not current_user.business_id or staff.business_id != current_user.business_id:
        abort(403)

    if staff.cash_balance and staff.cash_balance > 0:
        handover = CashHandover(
            amount=staff.cash_balance,
            user_id=staff.id,
            manager_id=current_user.id
        )
        db.session.add(handover)
        
        staff.cash_balance = 0.0
        db.session.commit()
        flash(f'Successfully received ₹{handover.amount:.2f} from {staff.username}. Their balance is now zero.')
    else:
        flash(f'{staff.username} has no cash balance to hand over.')
        
    return redirect(url_for('manager.dashboard'))


@bp.route('/reports')
@login_required
@manager_required
@subscription_required
def reports():
    if not current_user.business_id:
        flash("You are not assigned to a business to view reports.", "warning")
        return redirect(url_for('manager.dashboard'))

    today = date.today()
    business_id = current_user.business_id
    IST = ZoneInfo("Asia/Kolkata")

    # --- Monthly Report Logic ---
    try:
        report_year = int(request.args.get('year', today.year))
        report_month = int(request.args.get('month', today.month))
    except (ValueError, TypeError):
        report_year, report_month = today.year, today.month

    num_days_in_month = calendar.monthrange(report_year, report_month)[1]
    start_of_month = datetime(report_year, report_month, 1)
    end_of_month = datetime(report_year, report_month, num_days_in_month, 23, 59, 59)
    start_utc_month = start_of_month.replace(tzinfo=IST).astimezone(ZoneInfo("UTC"))
    end_utc_month = end_of_month.replace(tzinfo=IST).astimezone(ZoneInfo("UTC"))

    # --- Monthly Sales Calculations ---
    monthly_jar_sales = db.session.query(func.sum(DailyLog.amount_collected)).join(Customer).filter(
        Customer.business_id == business_id, DailyLog.timestamp.between(start_utc_month, end_utc_month)
    ).scalar() or 0.0
    
    monthly_product_sales_total = db.session.query(func.sum(ProductSale.total_amount)).filter(
        ProductSale.business_id == business_id, ProductSale.timestamp.between(start_utc_month, end_utc_month)
    ).scalar() or 0.0

    monthly_event_sales = db.session.query(func.sum(EventBooking.final_amount)).join(Customer).filter(
        Customer.business_id == business_id,
        EventBooking.status == 'Completed',
        EventBooking.collection_timestamp.between(start_utc_month, end_utc_month)
    ).scalar() or 0.0
    
    total_monthly_sales = monthly_jar_sales + monthly_product_sales_total + monthly_event_sales

    # --- Monthly Expense & Wage Calculation ---
    monthly_expenses_total = db.session.query(func.sum(Expense.amount)).join(User).filter(
        User.business_id == business_id, Expense.timestamp.between(start_utc_month, end_utc_month)
    ).scalar() or 0.0
    
    # --- Monthly Summaries ---
    customer_summary = db.session.query(
        Customer.name, func.sum(DailyLog.jars_delivered).label('total_jars'), func.sum(DailyLog.amount_collected).label('total_amount')
    ).join(DailyLog).filter(
        Customer.business_id == business_id, DailyLog.timestamp.between(start_utc_month, end_utc_month)
    ).group_by(Customer.name).order_by(func.sum(DailyLog.amount_collected).desc()).all()

    monthly_product_summary = db.session.query(
        ProductSale.product_name, func.sum(ProductSale.quantity).label('total_quantity'), func.sum(ProductSale.total_amount).label('total_amount')
    ).filter(
        ProductSale.business_id == business_id, ProductSale.timestamp.between(start_utc_month, end_utc_month)
    ).group_by(ProductSale.product_name).all()

    booking_logs = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == business_id,
        EventBooking.status == 'Completed',
        EventBooking.collection_timestamp.between(start_utc_month, end_utc_month)
    ).order_by(EventBooking.collection_timestamp.desc()).all()
    total_jars_lost = sum((booking.quantity - booking.jars_returned) for booking in booking_logs if booking.jars_returned is not None)

    staff_members = User.query.filter_by(role='staff', business_id=business_id).all()
    staff_monthly_summary = []
    for staff in staff_members:
        daily_jars_subquery = db.session.query(
            cast(DailyLog.timestamp, Date).label('delivery_date'), func.sum(DailyLog.jars_delivered).label('jars_sum')
        ).filter(
            DailyLog.user_id == staff.id, DailyLog.timestamp.between(start_utc_month, end_utc_month)
        ).group_by('delivery_date').subquery()

        full_days = db.session.query(func.count(daily_jars_subquery.c.delivery_date)).filter(daily_jars_subquery.c.jars_sum >= 50).scalar()
        half_days = db.session.query(func.count(daily_jars_subquery.c.delivery_date)).filter(
            daily_jars_subquery.c.jars_sum > 0, daily_jars_subquery.c.jars_sum < 50
        ).scalar()
        
        working_days = full_days + half_days
        absent_days = num_days_in_month - working_days

        total_wages = db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == staff.id, Expense.description.like('Daily Wage%'), Expense.timestamp.between(start_utc_month, end_utc_month)
        ).scalar() or 0.0

        staff_monthly_summary.append({
            'username': staff.username, 'full_days': full_days, 'half_days': half_days, 
            'absent_days': absent_days, 'total_wages': total_wages
        })

    # --- Daily Report Logic ---
    report_date_str = request.args.get('report_date', today.isoformat())
    try: report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
    except ValueError: report_date = today

    start_utc_day = datetime.combine(report_date, datetime.min.time(), tzinfo=IST).astimezone(ZoneInfo("UTC"))
    end_utc_day = datetime.combine(report_date, datetime.max.time(), tzinfo=IST).astimezone(ZoneInfo("UTC"))

    daily_sales = db.session.query(DailyLog).join(Customer).filter(
        Customer.business_id == business_id, DailyLog.timestamp.between(start_utc_day, end_utc_day)).all()
    daily_expenses = db.session.query(Expense).join(User).filter(
        User.business_id == business_id, Expense.timestamp.between(start_utc_day, end_utc_day)).all()
    daily_product_sales = db.session.query(ProductSale).filter(
        ProductSale.business_id == business_id, ProductSale.timestamp.between(start_utc_day, end_utc_day)).all()
    
    daily_event_sales = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == business_id,
        EventBooking.status == 'Completed',
        EventBooking.collection_timestamp.between(start_utc_day, end_utc_day)
    ).all()
    
    total_daily_sales = sum(s.amount_collected for s in daily_sales) + sum(p.total_amount for p in daily_product_sales) + sum(e.final_amount for e in daily_event_sales if e.final_amount)
    total_daily_expenses = sum(e.amount for e in daily_expenses)
    
    attendance = []
    for staff in staff_members:
        jars_sold = db.session.query(func.sum(DailyLog.jars_delivered)).filter(
            DailyLog.user_id == staff.id, DailyLog.timestamp.between(start_utc_day, end_utc_day)).scalar() or 0
        status = "Absent"
        if 0 < jars_sold < 50: status = "Half Day"
        elif jars_sold >= 50: status = "Full Day"
        attendance.append({'username': staff.username, 'jars_sold': jars_sold, 'status': status})

    cash_handover_logs = db.session.query(CashHandover).join(
        User, CashHandover.user_id == User.id
    ).filter(
        User.business_id == business_id,
        CashHandover.manager_id == current_user.id,
        CashHandover.timestamp.between(start_utc_month, end_utc_month)
    ).order_by(CashHandover.timestamp.desc()).all()

    # --- Monthly Leads from Product Sales ---
    monthly_leads = db.session.query(ProductSale).filter(
        ProductSale.business_id == business_id,
        ProductSale.timestamp.between(start_utc_month, end_utc_month)
    ).order_by(ProductSale.timestamp.desc()).all()

    return render_template('manager/reports.html', title="Reports",
        report_month=report_month, report_year=report_year,
        total_monthly_sales=total_monthly_sales, total_monthly_expenses=monthly_expenses_total,
        customer_summary=customer_summary, monthly_product_summary=monthly_product_summary,
        staff_monthly_summary=staff_monthly_summary,
        booking_logs=booking_logs,
        total_jars_lost=total_jars_lost,
        report_date=report_date, daily_sales=daily_sales, daily_expenses=daily_expenses,
        daily_product_sales=daily_product_sales,
        daily_event_sales=daily_event_sales,
        attendance=attendance,
        total_daily_sales=total_daily_sales, total_daily_expenses=total_daily_expenses,
        cash_handover_logs=cash_handover_logs,
        monthly_leads=monthly_leads,  # Add this line
        current_year=today.year)


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def settings():
    business = Business.query.filter_by(id=current_user.business_id).first_or_404()
    form = BusinessSettingsForm(obj=business)
    if form.validate_on_submit():
        business.new_jar_price = form.new_jar_price.data
        business.new_dispenser_price = form.new_dispenser_price.data
        business.full_day_jar_count = form.full_day_jar_count.data
        business.half_day_jar_count = form.half_day_jar_count.data
        db.session.commit()
        flash('Business settings have been updated.')
        return redirect(url_for('manager.dashboard'))
    return render_template('manager/settings.html', title="Business Settings", form=form)


@bp.route('/stock', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def stock_management():
    business = Business.query.filter_by(id=current_user.business_id).first_or_404()
    form = StockForm()

    # Query for jars that are out with customers for events
    outstanding_bookings = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        EventBooking.status == 'Delivered'
    ).order_by(EventBooking.event_date).all()

    if form.validate_on_submit():
        jars_added = form.jars_added.data or 0
        dispensers_added = form.dispensers_added.data or 0

        if jars_added < 0 or dispensers_added < 0:
            flash("Cannot add negative stock values.", "danger")
            return redirect(url_for('manager.stock_management'))

        if business.jar_stock is None: business.jar_stock = 0
        if business.dispenser_stock is None: business.dispenser_stock = 0

        business.jar_stock += jars_added
        business.dispenser_stock += dispensers_added
        db.session.commit()
        flash(f'Stock updated. Added {jars_added} jars and {dispensers_added} dispensers.', 'success')
        return redirect(url_for('manager.stock_management'))

    return render_template(
        'manager/stock_management.html', 
        title="Stock Management", 
        form=form, 
        business=business,
        outstanding_bookings=outstanding_bookings
    )


# --- STAFF MANAGEMENT ROUTES ---
@bp.route('/staff')
@login_required
@manager_required
@subscription_required
def staff_list():
    staff_members = User.query.filter_by(
        role='staff', business_id=current_user.business_id
    ).order_by(User.username).all()
    return render_template('manager/list_staff.html', title="Manage Staff", staff_members=staff_members)

@bp.route('/staff/add', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def add_staff():
    form = AddStaffForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            role='staff',
            business_id=current_user.business_id,
            mobile_number=form.mobile_number.data,
            address=form.address.data,
            daily_wage=form.daily_wage.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit() # Commit to get user.id for the filename

        if form.id_proof.data:
            f = form.id_proof.data
            filename = secure_filename(f"{user.id}_{user.username}_{f.filename}")
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            user.id_proof_filename = filename
            db.session.commit()

        flash(f'Staff member "{user.username}" has been created.', 'success')
        return redirect(url_for('manager.staff_list'))
    return render_template('manager/add_staff_form.html', title="Add New Staff", form=form)

@bp.route('/staff/edit/<int:staff_id>', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def edit_staff(staff_id):
    staff = User.query.get_or_404(staff_id)
    if staff.business_id != current_user.business_id or staff.role != 'staff':
        abort(403)
        
    form = EditStaffByManagerForm(original_username=staff.username, obj=staff)
    if form.validate_on_submit():
        staff.username = form.username.data
        staff.mobile_number = form.mobile_number.data
        staff.address = form.address.data
        staff.daily_wage = form.daily_wage.data
        
        if form.password.data:
            staff.set_password(form.password.data)
            
        if form.id_proof.data:
            if staff.id_proof_filename:
                try: os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], staff.id_proof_filename))
                except OSError: pass
            
            f = form.id_proof.data
            filename = secure_filename(f"{staff.id}_{staff.username}_{f.filename}")
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            staff.id_proof_filename = filename
            
        db.session.commit()
        flash(f'Staff member {staff.username} has been updated.', 'success')
        return redirect(url_for('manager.staff_list'))

    return render_template('manager/edit_staff_form.html', title="Edit Staff", form=form, staff=staff)

@bp.route('/confirm_booking/<int:booking_id>', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def confirm_booking(booking_id):
    booking = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == current_user.business_id, EventBooking.id == booking_id
    ).first_or_404()
    
    form = EventConfirmationForm()
    if form.validate_on_submit():
        business = Business.query.get(current_user.business_id)
        
        # Check stock for both jars and dispensers
        if business.jar_stock < booking.quantity:
            flash(f'Not enough jar stock to confirm. Only {business.jar_stock} jars available.', 'danger')
            return redirect(url_for('manager.dashboard'))
        if business.dispenser_stock < (booking.dispensers_booked or 0):
            flash(f'Not enough dispenser stock to confirm. Only {business.dispenser_stock} dispensers available.', 'danger')
            return redirect(url_for('manager.dashboard'))
            
        # Deduct stock for both
        business.jar_stock -= booking.quantity
        business.dispenser_stock -= (booking.dispensers_booked or 0)
        
        booking.amount = form.amount.data
        booking.paid_to_manager = form.paid_to_manager.data
        booking.status = 'Confirmed'
        booking.confirmed_by_id = current_user.id
        db.session.commit()
        flash('Event booking confirmed and stock updated.')
        return redirect(url_for('manager.dashboard'))
        
    return render_template('manager/confirm_booking.html', title='Confirm Event Booking', form=form, booking=booking)


# --- ACCOUNT MANAGEMENT ROUTE ---
@bp.route('/account', methods=['GET', 'POST'])
@login_required
@manager_required
def account():
    password_form = ChangePasswordForm()
    if password_form.submit_password.data and password_form.validate_on_submit():
        user = User.query.get(current_user.id)
        user.set_password(password_form.password.data)
        db.session.commit()
        flash('Your password has been changed successfully.', 'success')
        return redirect(url_for('manager.account'))
        
    business = Business.query.get(current_user.business_id)
    return render_template('manager/account.html', title="My Account", password_form=password_form, business=business)

# --- EVENT BOOKING FOR MANAGERS ---
# This route reuses the logic and template from the delivery blueprint
@bp.route('/book_event', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def book_event():
    return redirect(url_for('delivery.book_event'))

# --- INVOICE MANAGEMENT ROUTES ---
@bp.route('/invoices')
@login_required
@manager_required
def list_invoices():
    page = request.args.get('page', 1, type=int)
    invoices = Invoice.query.filter_by(business_id=current_user.business_id).order_by(Invoice.issue_date.desc()).paginate(page=page, per_page=10)
    return render_template('manager/list_invoices.html', invoices=invoices, title="All Invoices")

@bp.route('/generate_invoice/<int:customer_id>', methods=['GET', 'POST'])
@login_required
@manager_required
def generate_invoice(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == 'POST':
        month = int(request.form['month'])
        year = int(request.form['year'])
        
        start_date = date(year, month, 1)
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        
        # --- Gather Data for Invoice ---
        total_amount = 0
        invoice_items = []
        
        # 1. Daily Jar Deliveries
        daily_logs = DailyLog.query.filter(
            DailyLog.customer_id == customer.id,
            DailyLog.timestamp >= start_date,
            DailyLog.timestamp <= end_date
        ).all()
        
        if daily_logs:
            total_jars = sum(log.jars_delivered for log in daily_logs)
            avg_price = sum(log.amount_collected for log in daily_logs) / total_jars if total_jars > 0 else customer.price_per_jar
            item_total = total_jars * avg_price
            invoice_items.append(InvoiceItem(description=f"Monthly Jar Supply ({start_date.strftime('%b %Y')})", quantity=total_jars, unit_price=avg_price, total=item_total))
            total_amount += item_total

        # 2. Event Bookings
        event_bookings = EventBooking.query.filter(
            EventBooking.customer_id == customer.id,
            EventBooking.status == 'Completed',
            EventBooking.collection_timestamp >= start_date,
            EventBooking.collection_timestamp <= end_date
        ).all()

        for booking in event_bookings:
            invoice_items.append(InvoiceItem(description=f"Event Booking on {booking.event_date.strftime('%d-%b')}", quantity=1, unit_price=booking.final_amount, total=booking.final_amount))
            total_amount += booking.final_amount

        # --- Create Invoice ---
        if not invoice_items:
            flash('No billable activity found for this customer in the selected month.', 'warning')
            return redirect(url_for('manager.generate_invoice', customer_id=customer_id))

        last_invoice_num = Invoice.query.filter_by(business_id=current_user.business_id).count()
        new_invoice_number = f"AQUA-{current_user.business_id}-{date.today().year}-{last_invoice_num + 1:04d}"

        new_invoice = Invoice(
            invoice_number=new_invoice_number,
            due_date=date.today() + timedelta(days=15),
            total_amount=total_amount,
            customer_id=customer.id,
            business_id=current_user.business_id
        )
        db.session.add(new_invoice)
        
        for item in invoice_items:
            new_invoice.items.append(item)
            
        db.session.commit()
        flash(f'Invoice {new_invoice_number} generated successfully!', 'success')
        return redirect(url_for('invoices.list_invoices'))

    return render_template('manager/generate_invoice_form.html', customer=customer, title="Generate Invoice")