from flask import render_template, flash, redirect, url_for, request, session, current_app
from flask_login import login_required, current_user
from app import db
from app.supplier import bp
from app.models import SupplierProduct, PurchaseOrder, PurchaseOrderItem, Business, Supplier
from app.decorators import manager_required, supplier_required
import razorpay
from datetime import datetime

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

# --- NEW ROUTE FOR SUPPLIER DASHBOARD ---
@bp.route('/supplier/dashboard')
@login_required
@supplier_required
def dashboard():
    supplier_profile = Supplier.query.filter_by(user_id=current_user.id).first_or_404()
    orders = PurchaseOrder.query.filter_by(supplier_id=supplier_profile.id).order_by(PurchaseOrder.order_date.desc()).all()
    return render_template('supplier/dashboard.html', title="Supplier Dashboard", orders=orders)
