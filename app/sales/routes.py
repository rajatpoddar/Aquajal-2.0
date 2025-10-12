# /water_supply_app/app/sales/routes.py

from flask import render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.sales import bp
from app.models import ProductSale, User, Business
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, IntegerField, SelectField
from wtforms.validators import DataRequired, Length, ValidationError, NumberRange
from app.manager.routes import subscription_required


class NewProductSaleForm(FlaskForm):
    product_name = SelectField('Product', choices=[('New Jar', 'New Jar'), ('Dispenser', 'Dispenser')], validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)], default=1)
    customer_name = StringField('Customer Name', validators=[DataRequired(), Length(max=120)])
    customer_mobile = StringField('Mobile Number', validators=[DataRequired(), Length(min=10, max=15)])
    submit = SubmitField('Record Sale')

    # Add a property to hold the business object for validation
    def __init__(self, business=None, *args, **kwargs):
        super(NewProductSaleForm, self).__init__(*args, **kwargs)
        self.business = business

    # Custom validator to check stock levels before submitting
    def validate_quantity(self, quantity):
        if not self.business:
            raise ValidationError("Could not identify the business for stock validation.")
        
        if self.product_name.data == 'New Jar':
            if quantity.data > self.business.jar_stock:
                raise ValidationError(f'Not enough jars in stock. Only {self.business.jar_stock} available.')
        elif self.product_name.data == 'Dispenser':
            if quantity.data > self.business.dispenser_stock:
                raise ValidationError(f'Not enough dispensers in stock. Only {self.business.dispenser_stock} available.')


@bp.route('/new_product', methods=['GET', 'POST'])
@login_required
@subscription_required
def new_product_sale():
    if current_user.role not in ['manager', 'staff'] or not current_user.business_id:
        flash("You are not assigned to a business and cannot perform this action.", "warning")
        return redirect(url_for('delivery.dashboard'))

    business = Business.query.get(current_user.business_id)
    # Pass the business object to the form for validation
    form = NewProductSaleForm(business=business)
    
    if form.validate_on_submit():
        product_name = form.product_name.data
        quantity = form.quantity.data
        
        # --- DEDUCT FROM STOCK ---
        if product_name == 'New Jar':
            business.jar_stock -= quantity
            price_per_item = business.new_jar_price
        else: # Dispenser
            business.dispenser_stock -= quantity
            price_per_item = business.new_dispenser_price

        total_amount = quantity * price_per_item
        
        sale = ProductSale(
            product_name=product_name,
            quantity=quantity,
            price_per_item=price_per_item,
            total_amount=total_amount,
            customer_name=form.customer_name.data,
            customer_mobile=form.customer_mobile.data,
            user_id=current_user.id,
            business_id=current_user.business_id
        )
        db.session.add(sale)

        user = User.query.get(current_user.id)
        if user.cash_balance is None: user.cash_balance = 0.0
        user.cash_balance += total_amount
        
        db.session.commit()
        
        flash(f'Sale of {quantity} {product_name}(s) for ₹{total_amount:.2f} recorded. Stock updated.', 'success')
        return redirect(url_for('delivery.dashboard'))

    return render_template('sales/new_product_sale.html', title='Sell New Product', form=form, business=business)