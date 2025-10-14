# /water_supply_app/app/customers/routes.py

from flask import render_template, flash, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.customers import bp
from app.models import Customer, User # Import User for validation
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, FloatField, PasswordField
from wtforms.validators import DataRequired, Length, Optional, ValidationError, Email
from sqlalchemy import or_

# Import the new decorator
from app.decorators import manager_required, subscription_required

class CustomerForm(FlaskForm):
    name = StringField('Customer Name', validators=[DataRequired(), Length(min=3, max=120)])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), Length(min=10, max=15)])
    email = StringField('Email Address', validators=[Optional(), Email()])
    password = PasswordField('Set/Change Password', validators=[Optional(), Length(min=4)])
    village = StringField('Village', validators=[DataRequired()])
    # --- MODIFIED LINES: Made Area and Landmark optional ---
    area = StringField('Area / Street', validators=[Optional()])
    landmark = StringField('Landmark', validators=[Optional()])
    daily_jars = IntegerField('Daily Jars Required', validators=[DataRequired()], default=1)
    price_per_jar = FloatField('Price per Jar (₹)', validators=[DataRequired()], default=20)
    submit = SubmitField('Save Customer')

    def __init__(self, original_username=None, original_email=None, *args, **kwargs):
        super(CustomerForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data == self.original_username:
            return
        if User.query.filter_by(username=username.data).first() or \
           Customer.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken. Please choose a different one.')

    def validate_email(self, email):
        if email.data and email.data != self.original_email:
            if Customer.query.filter_by(email=email.data).first() or \
               User.query.filter_by(email=email.data).first():
                raise ValidationError('This email address is already registered.')


@bp.route('/list')
@login_required
@manager_required
@subscription_required
def index():
    query = Customer.query.filter_by(business_id=current_user.business_id)
    
    # Search functionality
    search_term = request.args.get('search', '')
    if search_term:
        query = query.filter(or_(
            Customer.name.ilike(f'%{search_term}%'),
            Customer.mobile_number.ilike(f'%{search_term}%')
        ))

    # Sorting functionality
    sort_by = request.args.get('sort', 'name')
    if sort_by == 'area':
        query = query.order_by(Customer.area)
    elif sort_by == 'village':
        query = query.order_by(Customer.village)
    else:
        query = query.order_by(Customer.name)
        
    customers = query.all()
    return render_template('customers/list_customers.html', customers=customers, title='All Customers', search_term=search_term, sort_by=sort_by)

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def add_customer():
    form = CustomerForm()
    if form.validate_on_submit():
        # --- MODIFIED LINE: Convert empty email string to None ---
        customer_email = form.email.data if form.email.data else None
        
        customer = Customer(
            name=form.name.data,
            username=form.username.data,
            mobile_number=form.mobile_number.data,
            # --- MODIFIED LINE: Use the sanitized email value ---
            email=customer_email,
            village=form.village.data,
            area=form.area.data,
            landmark=form.landmark.data,
            daily_jars=form.daily_jars.data,
            price_per_jar=form.price_per_jar.data,
            business_id=current_user.business_id
        )
        if form.password.data:
            customer.set_password(form.password.data)
        else:
            customer.set_password('123456')
            flash('Default password "123456" has been set for this customer.', 'info')

        db.session.add(customer)
        db.session.commit()
        flash(f'Customer "{form.name.data}" has been added successfully!', 'success')
        return redirect(url_for('customers.index'))
    return render_template('customers/customer_form.html', form=form, title='Add New Customer')

@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@manager_required
@subscription_required
def edit_customer(id):
    customer = Customer.query.filter_by(id=id, business_id=current_user.business_id).first_or_404()
    form = CustomerForm(original_username=customer.username, original_email=customer.email, obj=customer)
    if form.validate_on_submit():
        customer.name = form.name.data
        customer.username = form.username.data
        customer.mobile_number = form.mobile_number.data
        # --- MODIFIED LINE: Convert empty email string to None ---
        customer.email = form.email.data if form.email.data else None
        customer.village = form.village.data
        customer.area = form.area.data
        customer.landmark = form.landmark.data
        customer.daily_jars = form.daily_jars.data
        customer.price_per_jar = form.price_per_jar.data
        
        if form.password.data:
            customer.set_password(form.password.data)
        
        db.session.commit()
        flash(f'Customer "{customer.name}" has been updated.', 'success')
        return redirect(url_for('customers.index'))
    return render_template('customers/customer_form.html', form=form, title='Edit Customer')

@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@manager_required
@subscription_required
def delete_customer(id):
    customer = Customer.query.filter_by(id=id, business_id=current_user.business_id).first_or_404()
    db.session.delete(customer)
    db.session.commit()
    flash(f'Customer "{customer.name}" has been deleted.', 'danger')
    return redirect(url_for('customers.index'))

# API route for username check
@bp.route('/api/check_username')
@login_required
def check_username():
    username = request.args.get('username', '', type=str)
    if not username:
        return jsonify({'available': False})
    
    is_taken = User.query.filter_by(username=username).first() or \
               Customer.query.filter_by(username=username).first()
               
    return jsonify({'available': not is_taken})