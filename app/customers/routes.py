# /water_supply_app/app/customers/routes.py

from flask import render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.customers import bp
from app.models import Customer, User # Import User for validation
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, FloatField, PasswordField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

# This decorator ensures only managers and admins can access these routes
from app.manager.routes import manager_required

class CustomerForm(FlaskForm):
    name = StringField('Customer Name', validators=[DataRequired(), Length(min=3, max=120)])
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    mobile_number = StringField('Mobile Number', validators=[DataRequired(), Length(min=10, max=15)])
    password = PasswordField('Set/Change Password', validators=[Optional(), Length(min=4)])
    village = StringField('Village', validators=[DataRequired()])
    area = StringField('Area / Street', validators=[DataRequired()])
    landmark = StringField('Landmark', validators=[Optional()])
    daily_jars = IntegerField('Daily Jars Required', validators=[DataRequired()], default=1)
    price_per_jar = FloatField('Price per Jar (₹)', validators=[DataRequired()], default=20)
    submit = SubmitField('Save Customer')

    def __init__(self, original_username=None, *args, **kwargs):
        super(CustomerForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        # If the username hasn't changed during an edit, we don't need to validate it
        if username.data == self.original_username:
            return
            
        # Check if the new username exists in either the User or Customer table
        if User.query.filter_by(username=username.data).first() or \
           Customer.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken. Please choose a different one.')


@bp.route('/list')
@login_required
@manager_required
def index():
    customers = Customer.query.filter_by(business_id=current_user.business_id).order_by(Customer.name).all()
    return render_template('customers/list_customers.html', customers=customers, title='All Customers')

@bp.route('/add', methods=['GET', 'POST'])
@login_required
@manager_required
def add_customer():
    form = CustomerForm()
    if form.validate_on_submit():
        customer = Customer(
            name=form.name.data,
            username=form.username.data,
            mobile_number=form.mobile_number.data,
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
            # If no password is provided, set the mobile number as a default password
            customer.set_password(form.mobile_number.data)
            flash(f'No password was set. The default password for {form.username.data} is their mobile number: {form.mobile_number.data}', 'warning')

        db.session.add(customer)
        db.session.commit()
        flash(f'Customer "{form.name.data}" has been added successfully!', 'success')
        return redirect(url_for('customers.index'))
    return render_template('customers/customer_form.html', form=form, title='Add New Customer')

@bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@manager_required
def edit_customer(id):
    customer = Customer.query.filter_by(id=id, business_id=current_user.business_id).first_or_404()
    form = CustomerForm(original_username=customer.username, obj=customer)
    if form.validate_on_submit():
        customer.name = form.name.data
        customer.username = form.username.data
        customer.mobile_number = form.mobile_number.data
        customer.village = form.village.data
        customer.area = form.area.data
        customer.landmark = form.landmark.data
        customer.daily_jars = form.daily_jars.data
        customer.price_per_jar = form.price_per_jar.data
        
        # Only set password if a new one is typed into the form
        if form.password.data:
            customer.set_password(form.password.data)
        
        db.session.commit()
        flash(f'Customer "{customer.name}" has been updated.', 'success')
        return redirect(url_for('customers.index'))
    return render_template('customers/customer_form.html', form=form, title='Edit Customer')

@bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@manager_required
def delete_customer(id):
    customer = Customer.query.filter_by(id=id, business_id=current_user.business_id).first_or_404()
    # To maintain data integrity, you might want to handle related logs/requests here
    # instead of just deleting. For now, we delete.
    db.session.delete(customer)
    db.session.commit()
    flash(f'Customer "{customer.name}" has been deleted.', 'danger')
    return redirect(url_for('customers.index'))