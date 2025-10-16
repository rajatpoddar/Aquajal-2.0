from flask import render_template, flash, redirect, url_for, request, session, current_app, abort
from flask_login import login_required, current_user
from app import db
from app.supplier import bp
from app.models import SupplierProduct, PurchaseOrder, PurchaseOrderItem, Business, SupplierProfile, User
from app.decorators import manager_required, supplier_required
import razorpay
from datetime import date, datetime  # Correctly imported here
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, DateField, SelectField, TextAreaField, FloatField, IntegerField, PasswordField
from wtforms.validators import DataRequired, Optional, NumberRange, Length, EqualTo
from flask_wtf.file import FileField, FileAllowed
import os
from werkzeug.utils import secure_filename
from sqlalchemy import func, cast, Date
import calendar

class OrderStatusForm(FlaskForm):
    status = SelectField('Order Status', choices=[('Pending', 'Pending'), ('Confirmed', 'Confirmed'), ('Shipped', 'Shipped'), ('Delivered', 'Delivered'), ('Cancelled', 'Cancelled')], validators=[DataRequired()])
    delivery_date = DateField('Estimated Delivery Date', validators=[Optional()])
    submit = SubmitField('Update Status')

class ProductForm(FlaskForm):
    name = StringField('Product Name', validators=[DataRequired()])
    category = SelectField('Category', choices=[('Jars', 'Jars'), ('Dispensers', 'Dispensers'), ('Chemicals', 'Chemicals'), ('Other', 'Other')], validators=[DataRequired()])
    description = TextAreaField('Description')
    price = FloatField('Selling Price (₹)', validators=[DataRequired(), NumberRange(min=0)])
    manufacture_price = FloatField('Manufacturing Cost (₹)', validators=[Optional(), NumberRange(min=0)])
    discount_percentage = IntegerField('Discount (%)', validators=[Optional(), NumberRange(min=0, max=100)], default=0)
    submit = SubmitField('Save Product')

class SupplierProfileForm(FlaskForm):
    shop_name = StringField('Shop Name', validators=[DataRequired(), Length(max=120)])
    address = TextAreaField('Address', validators=[Optional(), Length(max=250)])
    mobile_number = StringField('Mobile Number', validators=[Optional(), Length(max=15)])
    id_proof = FileField('ID Proof Image (JPG, PNG)', validators=[
        Optional(),
        FileAllowed(['jpg', 'png', 'jpeg'], 'Images only!')
    ])
    submit_profile = SubmitField('Update Profile')

class ChangePasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat New Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match.')])
    submit_password = SubmitField('Change Password')


# --- HELPER FUNCTIONS ---
def get_cart():
    return session.get('procurement_cart', {})

def clear_cart():
    session.pop('procurement_cart', None)

# --- ROUTES FOR MANAGER PROCUREMENT ---
@bp.route('/procurement/browse')
@login_required
@manager_required
def browse_products():
    products = SupplierProduct.query.order_by(SupplierProduct.supplier_id, SupplierProduct.name).all()
    return render_template('supplier/browse_products.html', title="Browse Supplier Products", products=products)

@bp.route('/procurement/add_to_cart', methods=['POST'])
@login_required
@manager_required
def add_to_cart():
    cart = get_cart()
    product_id = request.form.get('product_id')
    quantity = request.form.get('quantity', 1, type=int)

    if product_id and quantity > 0:
        cart[product_id] = cart.get(product_id, 0) + quantity
        session['procurement_cart'] = cart
        flash(f'Item added to cart.')
    else:
        flash('Invalid item or quantity.', 'danger')
    
    return redirect(url_for('supplier.browse_products'))

@bp.route('/procurement/cart')
@login_required
@manager_required
def view_cart():
    cart = get_cart()
    if not cart:
        flash('Your cart is empty.')
        return redirect(url_for('supplier.browse_products'))

    cart_items = []
    total_amount = 0.0
    for product_id, quantity in cart.items():
        product = SupplierProduct.query.get(product_id)
        if product:
            subtotal = product.price * quantity
            total_amount += subtotal
            cart_items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    
    return render_template('supplier/cart.html', title="Your Shopping Cart", cart_items=cart_items, total_amount=total_amount)

@bp.route('/procurement/checkout', methods=['GET'])
@login_required
@manager_required
def procurement_checkout():
    cart = get_cart()
    if not cart:
        return redirect(url_for('supplier.view_cart'))

    cart_items = []
    total_amount = 0.0
    for product_id, quantity in cart.items():
        product = SupplierProduct.query.get(product_id)
        if product:
            subtotal = product.price * quantity
            total_amount += subtotal
            cart_items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})

    client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], current_app.config['RAZORPAY_KEY_SECRET']))
    payment_data = {
        'amount': int(total_amount * 100),
        'currency': 'INR',
        'receipt': f'procure_rcptid_{current_user.business_id}_{datetime.now().timestamp()}'
    }
    order = client.order.create(data=payment_data)

    return render_template(
        'manager/procurement_checkout.html', 
        title="Checkout", 
        cart_items=cart_items, 
        total_amount=total_amount,
        order=order,
        razorpay_key_id=current_app.config['RAZORPAY_KEY_ID']
    )

@bp.route('/procurement/checkout/cod', methods=['POST'])
@login_required
@manager_required
def procurement_cod_checkout():
    cart = get_cart()
    if not cart:
        flash('Your session expired or cart is empty.', 'warning')
        return redirect(url_for('supplier.browse_products'))
    
    total_amount = 0
    supplier_id = None
    items_to_add = []
    
    for product_id, quantity in cart.items():
        product = SupplierProduct.query.get(product_id)
        if product:
            if not supplier_id:
                supplier_id = product.supplier_id
            elif supplier_id != product.supplier_id:
                flash('Cannot order from multiple suppliers at once.', 'danger')
                return redirect(url_for('supplier.view_cart'))
            
            price_at_purchase = product.price
            total_amount += quantity * price_at_purchase
            items_to_add.append(PurchaseOrderItem(product_id=product_id, quantity=quantity, price_at_purchase=price_at_purchase))

    if items_to_add:
        order = PurchaseOrder(
            business_id=current_user.business_id,
            supplier_id=supplier_id,
            total_amount=total_amount,
            status='COD - Placed'
        )
        order.items.extend(items_to_add)
        db.session.add(order)
        db.session.commit()
        clear_cart()
        flash('Your order has been placed successfully via Cash on Delivery!', 'success')
        return redirect(url_for('manager.dashboard'))

    flash('Something went wrong with your order.', 'danger')
    return redirect(url_for('supplier.view_cart'))

@bp.route('/procurement/payment-success', methods=['POST'])
@login_required
@manager_required
def procurement_payment_success():
    cart = get_cart()
    if not cart:
        flash('Your session expired or cart is empty.', 'warning')
        return redirect(url_for('supplier.browse_products'))

    data = request.form
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')
    
    client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], current_app.config['RAZORPAY_KEY_SECRET']))
    
    try:
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }
        client.utility.verify_payment_signature(params_dict)

        total_amount = 0
        supplier_id = None
        items_to_add = []

        for product_id, quantity in cart.items():
            product = SupplierProduct.query.get(product_id)
            if product:
                if not supplier_id:
                    supplier_id = product.supplier_id
                price_at_purchase = product.price
                total_amount += quantity * price_at_purchase
                items_to_add.append(PurchaseOrderItem(product_id=product_id, quantity=quantity, price_at_purchase=price_at_purchase))
        
        if items_to_add:
            order = PurchaseOrder(
                business_id=current_user.business_id,
                supplier_id=supplier_id,
                total_amount=total_amount,
                status='Paid - Online'
            )
            order.items.extend(items_to_add)
            db.session.add(order)
            db.session.commit()
            clear_cart()
            flash('Payment successful and your order has been placed!', 'success')
            return redirect(url_for('manager.dashboard'))

    except Exception as e:
        flash(f'Payment verification failed: {e}. Please try again or contact support.', 'danger')
        return redirect(url_for('supplier.procurement_checkout'))

    flash('Something went wrong with your order.', 'danger')
    return redirect(url_for('supplier.view_cart'))

# --- SUPPLIER DASHBOARD AND PRODUCT MANAGEMENT ---
@bp.route('/dashboard')
@login_required
@supplier_required
def dashboard():
    supplier_profile = SupplierProfile.query.filter_by(user_id=current_user.id).first_or_404()
    orders = PurchaseOrder.query.filter_by(supplier_id=supplier_profile.id).order_by(PurchaseOrder.order_date.desc()).all()
    return render_template('supplier/dashboard.html', title="Supplier Dashboard", orders=orders)

@bp.route('/products')
@login_required
@supplier_required
def product_list():
    supplier_profile = SupplierProfile.query.filter_by(user_id=current_user.id).first_or_404()
    products = SupplierProduct.query.filter_by(supplier_id=supplier_profile.id).order_by(SupplierProduct.name).all()
    return render_template('supplier/product_list.html', title="Manage My Products", products=products)

@bp.route('/add_product', methods=['GET', 'POST'])
@login_required
@supplier_required
def add_product():
    form = ProductForm()
    if form.validate_on_submit():
        supplier_profile = SupplierProfile.query.filter_by(user_id=current_user.id).first_or_404()
        product = SupplierProduct(
            name=form.name.data,
            category=form.category.data,
            description=form.description.data,
            price=form.price.data,
            manufacture_price=form.manufacture_price.data,
            discount_percentage=form.discount_percentage.data,
            supplier_id=supplier_profile.id
        )
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully!', 'success')
        return redirect(url_for('supplier.product_list'))
    return render_template('supplier/product_form.html', title="Add New Product", form=form)


@bp.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
@supplier_required
def edit_product(product_id):
    product = SupplierProduct.query.get_or_404(product_id)
    if product.supplier.user_id != current_user.id:
        abort(403)
    form = ProductForm(obj=product)
    if form.validate_on_submit():
        product.name = form.name.data
        product.category = form.category.data
        product.description = form.description.data
        product.price = form.price.data
        product.manufacture_price = form.manufacture_price.data
        product.discount_percentage = form.discount_percentage.data
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('supplier.product_list'))
    return render_template('supplier/product_form.html', title="Edit Product", form=form)


@bp.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
@supplier_required
def delete_product(product_id):
    product = SupplierProduct.query.get_or_404(product_id)
    if product.supplier.user_id != current_user.id:
        abort(403)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('supplier.product_list'))


@bp.route('/order_details/<int:order_id>', methods=['GET', 'POST'])
@login_required
@supplier_required
def order_details(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)
    if order.supplier.user_id != current_user.id:
        abort(403)
    
    is_locked = order.status in ['Delivered', 'Cancelled']
    form = OrderStatusForm()

    if form.validate_on_submit() and not is_locked:
        original_status = order.status
        new_status = form.status.data
        
        order.status = new_status
        order.delivery_date = form.delivery_date.data

        if new_status == 'Delivered' and original_status != 'Delivered':
            business = Business.query.get(order.business_id)
            if business:
                for item in order.items:
                    if item.product.category == 'Jars':
                        business.jar_stock += item.quantity
                    elif item.product.category == 'Dispensers':
                        business.dispenser_stock += item.quantity
                flash(f'Stock for {business.name} has been updated.', 'info')

        if new_status == 'Delivered' and not order.invoice_number:
            order.invoice_number = f"INV-{order.id}-{datetime.utcnow().strftime('%Y%m%d')}"
        
        db.session.commit()
        flash('Order status updated.', 'success')
        return redirect(url_for('supplier.order_details', order_id=order.id))

    form.status.data = order.status
    form.delivery_date.data = order.delivery_date
    manager = User.query.filter_by(business_id=order.business_id, role='manager').first()
    return render_template('supplier/order_details.html', title=f"Order #{order.id} Details", order=order, form=form, manager=manager, is_locked=is_locked)

@bp.route('/invoice/<int:order_id>')
@login_required
@supplier_required
def view_procurement_invoice(order_id):
    order = PurchaseOrder.query.get_or_404(order_id)
    if order.supplier.user_id != current_user.id:
        abort(403)
    manager = User.query.filter_by(business_id=order.business_id, role='manager').first()
    return render_template('procurement/invoice_template.html', order=order, manager=manager)

@bp.route('/account', methods=['GET', 'POST'])
@login_required
@supplier_required
def account():
    user = User.query.get(current_user.id)
    profile = user.supplier_profile
    
    profile_form = SupplierProfileForm(obj=profile)
    profile_form.mobile_number.data = user.mobile_number
    
    password_form = ChangePasswordForm()

    if profile_form.submit_profile.data and profile_form.validate_on_submit():
        profile.shop_name = profile_form.shop_name.data
        profile.address = profile_form.address.data
        user.mobile_number = profile_form.mobile_number.data

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
        flash('Your profile has been updated.', 'success')
        return redirect(url_for('supplier.account'))
        
    if password_form.submit_password.data and password_form.validate_on_submit():
        user.set_password(password_form.password.data)
        db.session.commit()
        flash('Your password has been changed successfully.', 'success')
        return redirect(url_for('supplier.account'))

    return render_template('supplier/account.html', title="My Account", profile_form=profile_form, password_form=password_form, user=user)

@bp.route('/reports')
@login_required
@supplier_required
def reports():
    supplier_profile = SupplierProfile.query.filter_by(user_id=current_user.id).first_or_404()
    today = date.today()
    
    try:
        report_year = int(request.args.get('year', today.year))
        report_month = int(request.args.get('month', today.month))
    except (ValueError, TypeError):
        report_year, report_month = today.year, today.month

    start_of_month = datetime(report_year, report_month, 1)
    end_of_month = start_of_month.replace(day=calendar.monthrange(report_year, report_month)[1])

    sales_items = db.session.query(
        PurchaseOrderItem.quantity,
        PurchaseOrderItem.price_at_purchase,
        SupplierProduct.manufacture_price,
        SupplierProduct.name
    ).join(PurchaseOrder).join(SupplierProduct).filter(
        PurchaseOrder.supplier_id == supplier_profile.id,
        PurchaseOrder.status == 'Delivered',
        cast(PurchaseOrder.order_date, Date) >= start_of_month.date(),
        cast(PurchaseOrder.order_date, Date) <= end_of_month.date()
    ).all()

    total_sales_amount = 0
    total_cost = 0
    product_summary = {}

    for item in sales_items:
        sale_value = item.quantity * item.price_at_purchase
        cost_value = item.quantity * (item.manufacture_price or 0)
        
        total_sales_amount += sale_value
        total_cost += cost_value

        if item.name not in product_summary:
            product_summary[item.name] = {'quantity': 0, 'sales': 0, 'income': 0}
        
        product_summary[item.name]['quantity'] += item.quantity
        product_summary[item.name]['sales'] += sale_value
        product_summary[item.name]['income'] += (sale_value - cost_value)

    net_income = total_sales_amount - total_cost

    return render_template('supplier/reports.html',
                           title="Monthly Report",
                           report_month=report_month,
                           report_year=report_year,
                           current_year=today.year,
                           total_sales_amount=total_sales_amount,
                           total_cost=total_cost,
                           net_income=net_income,
                           product_summary=product_summary)