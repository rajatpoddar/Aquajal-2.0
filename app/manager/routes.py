# /water_supply_app/app/manager/routes.py

from flask import render_template, flash, redirect, url_for, request, abort, current_app
from flask_login import login_required, current_user
from app import db
from app.manager import bp
from app.models import User, DailyLog, Expense, CashHandover, ProductSale, Customer, Business, JarRequest, EventBooking
from functools import wraps
from datetime import date, datetime
from sqlalchemy import func
from zoneinfo import ZoneInfo
import os
from werkzeug.utils import secure_filename

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, FloatField, SubmitField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Optional, Length, ValidationError


# --- Forms ---
class BusinessSettingsForm(FlaskForm):
    new_jar_price = FloatField('New Jar Price (₹)', validators=[DataRequired()])
    new_dispenser_price = FloatField('New Dispenser Price (₹)', validators=[DataRequired()])
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


# --- Custom Decorator for Manager/Admin Access ---
def manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['admin', 'manager']:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function


# --- Routes ---
@bp.route('/dashboard')
@login_required
@manager_required
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

    # --- FIX: Pass pending_bookings to the template ---
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
def reports():
    if not current_user.business_id:
        flash("You are not assigned to a business to view reports. Please contact the administrator.")
        return redirect(url_for('manager.dashboard'))

    IST = ZoneInfo("Asia/Kolkata")
    report_date_str = request.args.get('report_date', date.today().isoformat())
    try:
        report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
    except ValueError:
        report_date = date.today()

    start_of_day_ist = datetime.combine(report_date, datetime.min.time(), tzinfo=IST)
    end_of_day_ist = datetime.combine(report_date, datetime.max.time(), tzinfo=IST)

    start_utc = start_of_day_ist.astimezone(ZoneInfo("UTC"))
    end_utc = end_of_day_ist.astimezone(ZoneInfo("UTC"))

    sales = db.session.query(DailyLog).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        DailyLog.timestamp.between(start_utc, end_utc)
    ).all()
    
    expenses = db.session.query(Expense).join(User).filter(
        User.business_id == current_user.business_id,
        Expense.timestamp.between(start_utc, end_utc)
    ).all()

    product_sales = db.session.query(ProductSale).filter(
        ProductSale.business_id == current_user.business_id,
        ProductSale.timestamp.between(start_utc, end_utc)
    ).all()
    
    total_sales_amount = sum(s.amount_collected for s in sales) + sum(p.total_amount for p in product_sales)
    total_expense_amount = sum(e.amount for e in expenses)
    
    staff_members = User.query.filter_by(role='staff', business_id=current_user.business_id).all()
    attendance = []
    for staff in staff_members:
        jars_sold = db.session.query(func.sum(DailyLog.jars_delivered)).filter(
            DailyLog.user_id == staff.id,
            DailyLog.timestamp.between(start_utc, end_utc)
        ).scalar() or 0

        status = "Absent"
        if 0 < jars_sold < 50:
            status = "Half Day"
        elif jars_sold >= 50:
            status = "Full Day"
        
        attendance.append({'username': staff.username, 'jars_sold': jars_sold, 'status': status})

    return render_template(
        'manager/reports.html',
        title="Daily Reports",
        report_date=report_date,
        sales=sales,
        expenses=expenses,
        attendance=attendance,
        product_sales=product_sales,
        total_sales=total_sales_amount,
        total_expenses=total_expense_amount
    )


@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@manager_required
def settings():
    business = Business.query.filter_by(id=current_user.business_id).first_or_404()
    form = BusinessSettingsForm(obj=business)
    if form.validate_on_submit():
        business.new_jar_price = form.new_jar_price.data
        business.new_dispenser_price = form.new_dispenser_price.data
        db.session.commit()
        flash('Business settings have been updated.')
        return redirect(url_for('manager.dashboard'))
    return render_template('manager/settings.html', title="Business Settings", form=form)


@bp.route('/stock', methods=['GET', 'POST'])
@login_required
@manager_required
def stock_management():
    business = Business.query.filter_by(id=current_user.business_id).first_or_404()
    form = StockForm()
    if form.validate_on_submit():
        jars_added = form.jars_added.data or 0
        dispensers_added = form.dispensers_added.data or 0

        if jars_added < 0 or dispensers_added < 0:
            flash("Cannot add negative stock values.", "danger")
            return redirect(url_for('manager.stock_management'))

        if business.jar_stock is None:
            business.jar_stock = 0
        if business.dispenser_stock is None:
            business.dispenser_stock = 0

        business.jar_stock += jars_added
        business.dispenser_stock += dispensers_added
        db.session.commit()
        flash(f'Stock updated successfully. Added {jars_added} jars and {dispensers_added} dispensers.', 'success')
        return redirect(url_for('manager.stock_management'))
    return render_template('manager/stock_management.html', title="Stock Management", form=form, business=business)


# --- NEW STAFF MANAGEMENT ROUTES ---
@bp.route('/staff')
@login_required
@manager_required
def staff_list():
    staff_members = User.query.filter_by(
        role='staff', 
        business_id=current_user.business_id
    ).order_by(User.username).all()
    return render_template('manager/list_staff.html', title="Manage Staff", staff_members=staff_members)

@bp.route('/staff/edit/<int:staff_id>', methods=['GET', 'POST'])
@login_required
@manager_required
def edit_staff(staff_id):
    staff = User.query.get_or_404(staff_id)
    # Security check: manager can only edit staff in their own business
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
            # Delete old proof if it exists
            if staff.id_proof_filename:
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], staff.id_proof_filename))
                except OSError:
                    pass # File didn't exist, no problem
            
            # Save new proof
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
def confirm_booking(booking_id):
    booking = db.session.query(EventBooking).join(Customer).filter(
        Customer.business_id == current_user.business_id,
        EventBooking.id == booking_id
    ).first_or_404()
    
    form = EventConfirmationForm()
    if form.validate_on_submit():
        booking.amount = form.amount.data
        booking.paid_to_manager = form.paid_to_manager.data
        booking.status = 'Confirmed'
        booking.confirmed_by_id = current_user.id
        db.session.commit()
        flash('Event booking has been confirmed and assigned for delivery.')
        return redirect(url_for('manager.dashboard'))
        
    return render_template('manager/confirm_booking.html', title='Confirm Event Booking', form=form, booking=booking)