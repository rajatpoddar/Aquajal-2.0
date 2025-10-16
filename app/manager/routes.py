# /water_supply_app/app/manager/routes.py

from flask import render_template, flash, redirect, url_for, request, abort, current_app, session
from flask_login import login_required, current_user
from app import db
from app.manager import bp
from app.models import (User, DailyLog, Expense, CashHandover, ProductSale, Customer, 
                        Business, JarRequest, EventBooking, Invoice, InvoiceItem, 
                        SupplierProduct, SupplierProfile, PurchaseOrder, PurchaseOrderItem)
from functools import wraps
from datetime import date, datetime, timedelta
from sqlalchemy import func, cast, Date
from zoneinfo import ZoneInfo
import os
import calendar
from werkzeug.utils import secure_filename
import razorpay

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, FloatField, SubmitField, IntegerField, BooleanField, TextAreaField, RadioField
from wtforms.validators import DataRequired, Optional, Length, ValidationError, EqualTo, NumberRange, Email

# Import the form from the delivery blueprint and new email functions
from app.delivery.routes import EventBookingByStaffForm
from app.email import send_booking_confirmed_email_to_staff, send_booking_confirmed_email_to_customer, send_new_order_to_supplier_email

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
        if User.query.filter_by(username=username.data).first() or Customer.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken. Please choose a different one.')

class ChangePasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat New Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit_password = SubmitField('Change Password')

class AddToCartForm(FlaskForm):
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)], default=1)
    submit = SubmitField('Order Now')

class BusinessSettingsForm(FlaskForm):
    new_jar_price = FloatField('New Jar Price (₹)', validators=[DataRequired()])
    new_dispenser_price = FloatField('New Dispenser Price (₹)', validators=[DataRequired()])
    full_day_jar_count = IntegerField('Jars for Full Day Wage', validators=[DataRequired()])
    half_day_jar_count = IntegerField('Jars for Half Day Wage', validators=[DataRequired()])
    low_stock_threshold = IntegerField('Low Stock Alert Threshold (Jars)', validators=[DataRequired(), NumberRange(min=0)], default=20)
    low_stock_threshold_dispenser = IntegerField('Low Stock Alert Threshold (Dispensers)', validators=[DataRequired(), NumberRange(min=0)], default=5)
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
    quantity = IntegerField('Number of Jars', validators=[DataRequired(), NumberRange(min=1)])
    amount = FloatField('Total Amount (₹)', validators=[DataRequired()])
    paid_to_manager = BooleanField('Payment received directly by you (Manager)?')
    submit = SubmitField('Confirm Booking')

class CheckoutForm(FlaskForm):
    payment_method = RadioField('Payment Method', choices=[('cod', 'Cash on Delivery'), ('razorpay', 'Pay Online with Razorpay')], default='cod', validators=[DataRequired()])
    submit = SubmitField('Place Order')

class ManagerProfileForm(FlaskForm):
    # User fields
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email Address', validators=[Optional(), Email()])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    id_proof = FileField('ID Proof Image (JPG, PNG)', validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])
    
    # Business fields
    name = StringField('Business Name', validators=[DataRequired()])
    owner_name = StringField('Owner Name', validators=[DataRequired()])
    location = TextAreaField('Business Location', validators=[Optional(), Length(max=200)])

    submit_profile = SubmitField('Update Profile')

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(ManagerProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()
            if user is not None:
                raise ValidationError('Please use a different username.')
                
    def validate_email(self, email):
        if email.data and email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('This email address is already registered.')

# --- Custom Decorators ---
def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['admin', 'manager']:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role == 'admin':
            return f(*args, **kwargs)
        business = Business.query.get(current_user.business_id)
        if not business:
            flash("You are not associated with a business.", "danger")
            return redirect(url_for('auth.logout'))
        is_active = False
        now = datetime.utcnow()
        if business.subscription_status == 'active' and business.subscription_ends_at and business.subscription_ends_at > now:
            is_active = True
        elif business.subscription_status == 'trial' and business.trial_ends_at and business.trial_ends_at > now:
            is_active = True
        if not is_active:
            if business.subscription_status == 'trial':
                business.subscription_status = 'expired'
                db.session.commit()
            return redirect(url_for('billing.expired'))
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---
@bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def dashboard():
    staff_members = []
    total_staff_balance = 0.0
    pending_bookings = []
    total_dues = 0.0
    low_stock_jar = None
    low_stock_dispenser = None
    quick_order_form = None

    if not current_user.business_id:
        flash("You are not assigned to a business. Please contact the administrator.")
    else:
        business = Business.query.get(current_user.business_id)
        staff_members = User.query.filter_by(role='staff', business_id=current_user.business_id).order_by(User.username).all()
        total_staff_balance = sum(staff.cash_balance for staff in staff_members if staff.cash_balance)
        pending_bookings = db.session.query(EventBooking).join(Customer).filter(
            Customer.business_id == current_user.business_id,
            EventBooking.status == 'Pending'
        ).order_by(EventBooking.event_date).all()
        total_dues = db.session.query(func.sum(Customer.due_amount)).filter(Customer.business_id == current_user.business_id).scalar() or 0.0

        if business.jar_stock is not None and business.low_stock_threshold is not None and business.jar_stock <= business.low_stock_threshold:
            low_stock_jar_product = SupplierProduct.query.filter(SupplierProduct.name.ilike('%jar%')).order_by(SupplierProduct.price).first()
            if low_stock_jar_product:
                final_price = low_stock_jar_product.price
                if low_stock_jar_product.discount_percentage and low_stock_jar_product.discount_percentage > 0:
                    final_price = low_stock_jar_product.price - (low_stock_jar_product.price * low_stock_jar_product.discount_percentage / 100)
                low_stock_jar = {
                    'product': low_stock_jar_product,
                    'final_price': final_price
                }
        
        if business.dispenser_stock is not None and business.low_stock_threshold_dispenser is not None and business.dispenser_stock <= business.low_stock_threshold_dispenser:
            low_stock_dispenser_product = SupplierProduct.query.filter(SupplierProduct.name.ilike('%dispenser%')).order_by(SupplierProduct.price).first()
            if low_stock_dispenser_product:
                final_price = low_stock_dispenser_product.price
                if low_stock_dispenser_product.discount_percentage and low_stock_dispenser_product.discount_percentage > 0:
                    final_price = low_stock_dispenser_product.price - (low_stock_dispenser_product.price * low_stock_dispenser_product.discount_percentage / 100)
                low_stock_dispenser = {
                    'product': low_stock_dispenser_product,
                    'final_price': final_price
                }

        if low_stock_jar or low_stock_dispenser:
            quick_order_form = AddToCartForm()


    return render_template(
        'manager/dashboard.html',
        title="Manager Dashboard",
        staff_members=staff_members,
        total_staff_balance=total_staff_balance,
        pending_bookings=pending_bookings,
        total_dues=total_dues,
        low_stock_jar=low_stock_jar,
        low_stock_dispenser=low_stock_dispenser,
        quick_order_form=quick_order_form
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

@bp.route('/clear_dues/<int:customer_id>', methods=['POST'])
@login_required
@manager_required
@subscription_required
def clear_dues(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if customer.business_id != current_user.business_id:
        abort(403)
    
    amount_cleared = customer.due_amount
    customer.due_amount = 0.0
    
    DailyLog.query.filter_by(customer_id=customer.id, payment_status='Due').update({'payment_status': 'Paid'})
    Invoice.query.filter_by(customer_id=customer.id, status='Unpaid').update({'status': 'Paid'})
    
    db.session.commit()
    flash(f'Dues of ₹{amount_cleared:.2f} for {customer.name} have been cleared.', 'success')
    return redirect(url_for('customers.index'))


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

    monthly_expenses_total = db.session.query(func.sum(Expense.amount)).join(User).filter(
        User.business_id == business_id, Expense.timestamp.between(start_utc_month, end_utc_month)
    ).scalar() or 0.0
    
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
        monthly_leads=monthly_leads,
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
        business.low_stock_threshold = form.low_stock_threshold.data
        business.low_stock_threshold_dispenser = form.low_stock_threshold_dispenser.data  # This line was missing
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
        db.session.commit() 

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
    
    form = EventConfirmationForm(obj=booking)
    if form.validate_on_submit():
        business = Business.query.get(current_user.business_id)
        
        # Use the quantity from the form, not the original booking
        jars_to_book = form.quantity.data
        
        if business.jar_stock < jars_to_book:
            flash(f'Not enough jar stock to confirm. Only {business.jar_stock} jars available.', 'danger')
            return redirect(url_for('manager.dashboard'))
        if business.dispenser_stock < (booking.dispensers_booked or 0):
            flash(f'Not enough dispenser stock to confirm. Only {business.dispenser_stock} dispensers available.', 'danger')
            return redirect(url_for('manager.dashboard'))
            
        business.jar_stock -= jars_to_book
        business.dispenser_stock -= (booking.dispensers_booked or 0)
        
        booking.quantity = jars_to_book  # Update the booking's quantity
        booking.amount = form.amount.data
        booking.paid_to_manager = form.paid_to_manager.data
        booking.status = 'Confirmed'
        booking.confirmed_by_id = current_user.id
        db.session.commit()
        flash('Event booking confirmed and stock updated.')

        # --- EMAIL NOTIFICATION TO STAFF & CUSTOMER ---
        staff_users = User.query.filter_by(business_id=current_user.business_id, role='staff').all()
        for staff_member in staff_users:
            send_booking_confirmed_email_to_staff(booking, staff_member)
            
        send_booking_confirmed_email_to_customer(booking)
        # --- END EMAIL ---

        return redirect(url_for('manager.dashboard'))
        
    return render_template('manager/confirm_booking.html', title='Confirm Event Booking', form=form, booking=booking)

# --- ACCOUNT MANAGEMENT ROUTE ---
@bp.route('/account', methods=['GET', 'POST'])
@login_required
@manager_required
def account():
    user = User.query.get(current_user.id)
    business = Business.query.get(current_user.business_id)
    
    profile_form = ManagerProfileForm(original_username=user.username, original_email=user.email, obj=user)
    profile_form.name.data = business.name
    profile_form.owner_name.data = business.owner_name
    profile_form.location.data = business.location
    
    password_form = ChangePasswordForm()

    if profile_form.submit_profile.data and profile_form.validate_on_submit():
        user.username = profile_form.username.data
        user.mobile_number = profile_form.mobile_number.data
        user.email = profile_form.email.data
        
        business.name = profile_form.name.data
        business.owner_name = profile_form.owner_name.data
        business.location = profile_form.location.data

        if profile_form.id_proof.data:
            if user.id_proof_filename:
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], user.id_proof_filename))
                except OSError:
                    pass
            f = profile_form.id_proof.data
            filename = secure_filename(f"{user.id}_{user.username}_{f.filename}")
            f.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            user.id_proof_filename = filename

        db.session.commit()
        flash('Your profile and business details have been updated.', 'success')
        return redirect(url_for('manager.account'))
        
    if password_form.submit_password.data and password_form.validate_on_submit():
        user.set_password(password_form.password.data)
        db.session.commit()
        flash('Your password has been changed successfully.', 'success')
        return redirect(url_for('manager.account'))

    return render_template('manager/account.html', title="My Account", profile_form=profile_form, password_form=password_form, user=user, business=business)

# --- EVENT BOOKING FOR MANAGERS ---
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
        
        total_amount = 0
        invoice_items_data = []
        
        due_logs = DailyLog.query.filter(
            DailyLog.customer_id == customer.id,
            DailyLog.payment_status == 'Due',
            cast(DailyLog.timestamp, Date) >= start_date,
            cast(DailyLog.timestamp, Date) <= end_date
        ).all()

        outstanding_balance = sum(log.amount_collected for log in due_logs)

        if outstanding_balance > 0:
            invoice_items_data.append({
                'description': f"Outstanding Balance for {start_date.strftime('%b %Y')}",
                'quantity': 1,
                'unit_price': outstanding_balance,
                'total': outstanding_balance
            })
            total_amount += outstanding_balance

        event_bookings = EventBooking.query.filter(
            EventBooking.customer_id == customer.id,
            EventBooking.status == 'Completed',
            cast(EventBooking.collection_timestamp, Date) >= start_date,
            cast(EventBooking.collection_timestamp, Date) <= end_date
        ).all()

        for booking in event_bookings:
            invoice_items_data.append({
                'description': f"Event Booking on {booking.event_date.strftime('%d-%b')}",
                'quantity': 1,
                'unit_price': booking.final_amount,
                'total': booking.final_amount
            })
            total_amount += booking.final_amount

        if not invoice_items_data:
            flash('No billable activity found for this customer in the selected month.', 'warning')
            return redirect(url_for('manager.generate_invoice', customer_id=customer_id))

        status = 'Unpaid' if outstanding_balance > 0 else 'Paid'

        last_invoice_num = Invoice.query.filter_by(business_id=current_user.business_id).count()
        new_invoice_number = f"AQUA-{current_user.business_id}-{date.today().year}-{last_invoice_num + 1:04d}"

        new_invoice = Invoice(
            invoice_number=new_invoice_number,
            due_date=date.today() + timedelta(days=15),
            total_amount=total_amount,
            status=status,
            customer_id=customer.id,
            business_id=current_user.business_id
        )
        db.session.add(new_invoice)
        
        for item_data in invoice_items_data:
            item = InvoiceItem(**item_data)
            new_invoice.items.append(item)
            
        customer.due_amount = outstanding_balance if status == 'Unpaid' else 0.0

        db.session.commit()
        flash(f'Invoice {new_invoice_number} generated successfully!', 'success')
        return redirect(url_for('invoices.list_invoices'))

    return render_template('manager/generate_invoice_form.html', customer=customer, title="Generate Invoice")

# --- PROCUREMENT (SHOPPING) ROUTES ---

@bp.route('/procurement/browse')
@login_required
@manager_required
@subscription_required
def browse_products():
    """Allows managers to browse products from all suppliers."""
    subquery = db.session.query(
        SupplierProduct.name,
        SupplierProduct.supplier_id,
        func.max(SupplierProduct.id).label('max_id')
    ).group_by(SupplierProduct.name, SupplierProduct.supplier_id).subquery()

    products = db.session.query(
        SupplierProduct,
        SupplierProfile
    ).join(subquery, (SupplierProduct.id == subquery.c.max_id)
    ).join(SupplierProfile, (SupplierProduct.supplier_id == SupplierProfile.id)
    ).order_by(SupplierProduct.name, SupplierProduct.price).all()

    products_by_name = {}
    for product, supplier in products:
        if product.name not in products_by_name:
            products_by_name[product.name] = []
        
        final_price = product.price
        if product.discount_percentage and product.discount_percentage > 0:
            final_price = product.price - (product.price * product.discount_percentage / 100)
            
        products_by_name[product.name].append({
            'product': product, 
            'supplier': supplier,
            'final_price': final_price
        })

    return render_template('manager/browse_products.html', title='Browse Products', products_by_name=products_by_name)

@bp.route('/procurement/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
@manager_required
@subscription_required
def add_to_cart(product_id):
    product = SupplierProduct.query.get_or_404(product_id)
    try:
        quantity = int(request.form.get('quantity', 1))
        if quantity < 1:
            raise ValueError
    except ValueError:
        flash('Invalid quantity.', 'danger')
        return redirect(url_for('manager.browse_products'))

    cart = session.get('procurement_cart', {})
    cart_item = cart.get(str(product_id))

    if cart_item:
        cart_item['quantity'] += quantity
    else:
        cart[str(product_id)] = {'quantity': quantity}
    
    session['procurement_cart'] = cart
    flash(f'Added {quantity} x {product.name} to your cart.', 'success')
    return redirect(url_for('manager.browse_products'))

@bp.route('/procurement/cart')
@login_required
@manager_required
@subscription_required
def view_cart():
    cart = session.get('procurement_cart', {})
    cart_items = []
    total_amount = 0
    
    for product_id, item in cart.items():
        product = SupplierProduct.query.get(product_id)
        if product:
            final_price = product.price
            if product.discount_percentage > 0:
                final_price = product.price - (product.price * product.discount_percentage / 100)
            
            subtotal = final_price * item['quantity']
            total_amount += subtotal
            
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'final_price': final_price,
                'subtotal': subtotal
            })
            
    return render_template('manager/cart.html', title='Shopping Cart', cart_items=cart_items, total_amount=total_amount)

@bp.route('/procurement/update_cart/<int:product_id>', methods=['POST'])
@login_required
@manager_required
def update_cart(product_id):
    cart = session.get('procurement_cart', {})
    try:
        quantity = int(request.form['quantity'])
        if quantity > 0:
            cart[str(product_id)]['quantity'] = quantity
        else: # Remove if quantity is 0 or less
            del cart[str(product_id)]
    except (ValueError, KeyError):
        pass # Ignore errors
        
    session['procurement_cart'] = cart
    return redirect(url_for('manager.view_cart'))

@bp.route('/procurement/remove_from_cart/<int:product_id>')
@login_required
@manager_required
def remove_from_cart(product_id):
    cart = session.get('procurement_cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
    session['procurement_cart'] = cart
    return redirect(url_for('manager.view_cart'))

@bp.route('/procurement/checkout', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def checkout_cart():
    cart = session.get('procurement_cart', {})
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('manager.browse_products'))

    cart_items = []
    total_amount = 0
    
    for product_id, item in cart.items():
        product = SupplierProduct.query.get(product_id)
        if product:
            final_price = product.price * (1 - (product.discount_percentage or 0) / 100)
            subtotal = final_price * item['quantity']
            total_amount += subtotal
            cart_items.append({
                'product': product,
                'quantity': item['quantity'],
                'price_at_purchase': final_price
            })

    form = CheckoutForm()
    if form.validate_on_submit():
        if form.payment_method.data == 'cod':
            order = PurchaseOrder(
                business_id=current_user.business_id,
                supplier_id=cart_items[0]['product'].supplier_id,
                total_amount=total_amount,
                status='COD - Pending'
            )
            db.session.add(order)
            for item in cart_items:
                order_item = PurchaseOrderItem(
                    order=order,
                    product_id=item['product'].id,
                    quantity=item['quantity'],
                    price_at_purchase=item['price_at_purchase']
                )
                db.session.add(order_item)
            
            session.pop('procurement_cart', None)
            db.session.commit()
            flash('Your order has been placed successfully (Cash on Delivery)!', 'success')
            return redirect(url_for('manager.view_orders'))
        
        elif form.payment_method.data == 'razorpay':
            client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], current_app.config['RAZORPAY_KEY_SECRET']))
            payment_data = {
                'amount': int(total_amount * 100),
                'currency': 'INR',
            }
            order_data = client.order.create(data=payment_data)
            
            return render_template('manager/checkout.html', title='Checkout', form=form, cart_items=cart_items, total_amount=total_amount, order=order_data, razorpay_key_id=current_app.config['RAZORPAY_KEY_ID'])

    return render_template('manager/checkout.html', title='Checkout', form=form, cart_items=cart_items, total_amount=total_amount, order=None)

@bp.route('/procurement/orders')
@login_required
@manager_required
@subscription_required
def view_orders():
    """Lists all purchase orders placed by the manager's business."""
    orders = PurchaseOrder.query.filter_by(business_id=current_user.business_id).order_by(PurchaseOrder.order_date.desc()).all()
    return render_template('manager/view_orders.html', title='My Orders', orders=orders)

@bp.route('/procurement/invoice/<int:order_id>')
@login_required
@manager_required
def view_procurement_invoice(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)
    if order.business_id != current_user.business_id:
        abort(403)
    manager = User.query.filter_by(business_id=order.business_id, role='manager').first()
    return render_template('procurement/invoice_template.html', order=order, manager=manager)