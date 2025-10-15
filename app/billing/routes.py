# /water_supply_app/app/billing/routes.py

from flask import render_template, flash, redirect, url_for, request, current_app
from flask_login import current_user, login_required
from app import db
from app.billing import bp
from app.models import SubscriptionPlan, Coupon, Business, Payment
import razorpay
from datetime import datetime, timedelta

@bp.route('/expired')
@login_required
def expired():
    return render_template('billing/expired.html', title='Subscription Expired')

@bp.route('/subscribe')
@login_required
def subscribe():
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.duration_days).all()
    return render_template('billing/subscribe.html', title='Subscribe', plans=plans)

@bp.route('/checkout/<int:plan_id>', methods=['GET', 'POST'])
@login_required
def checkout(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    business = Business.query.get(current_user.business_id)
    
    # Use sale price as the base amount
    final_amount = plan.sale_price
    
    # Check if this is the first payment after the trial period
    is_first_payment = not business.subscription_plan_id
    if not is_first_payment:
        final_amount = plan.regular_price

    coupon_code = request.form.get('coupon')
    applied_coupon = False

    if request.method == 'POST' and coupon_code:
        coupon = Coupon.query.filter(Coupon.code.ilike(coupon_code), Coupon.is_active==True).first()
        if coupon and (not coupon.expiry_date or coupon.expiry_date.date() > datetime.today().date()):
            discount = (final_amount * coupon.discount_percentage) / 100
            final_amount -= discount
            applied_coupon = True
            flash(f'Coupon "{coupon_code}" applied! You get a {coupon.discount_percentage}% discount.', 'success')
        else:
            flash('Invalid or expired coupon code.', 'danger')

    client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], current_app.config['RAZORPAY_KEY_SECRET']))
    payment_data = {
        'amount': int(final_amount * 100),  # Amount in paise
        'currency': 'INR',
        'receipt': f'order_rcptid_{plan.id}_{business.id}_{datetime.now().timestamp()}'
    }
    order = client.order.create(data=payment_data)
    
    payment = Payment(
        business_id=business.id,
        razorpay_order_id=order['id'],
        amount=final_amount,
        status='created',
        subscription_plan_id=plan.id
    )
    db.session.add(payment)
    db.session.commit()

    return render_template('billing/checkout.html', title='Checkout', plan=plan, order=order, final_amount=final_amount, is_first_payment=is_first_payment, applied_coupon=applied_coupon, coupon_code=coupon_code, razorpay_key_id=current_app.config['RAZORPAY_KEY_ID'])


@bp.route('/cod_checkout/<int:plan_id>', methods=['POST'])
@login_required
def cod_checkout(plan_id):
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    business = Business.query.get(current_user.business_id)
    
    business.subscription_status = 'active'
    business.subscription_plan_id = plan.id
    
    start_date = datetime.utcnow()
    if business.subscription_ends_at and business.subscription_ends_at > start_date:
        start_date = business.subscription_ends_at
    
    business.subscription_ends_at = start_date + timedelta(days=plan.duration_days)
    
    payment = Payment(
        business_id=business.id,
        amount=0, # Or the actual amount if you want to track it
        status='cod',
        subscription_plan_id=plan.id
    )
    db.session.add(payment)

    db.session.commit()
    
    flash('Your order has been placed! Your subscription will be activated upon payment.', 'success')
    return redirect(url_for('manager.dashboard'))


@bp.route('/payment_success', methods=['POST'])
@login_required
def payment_success():
    data = request.form
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')

    payment = Payment.query.filter_by(razorpay_order_id=razorpay_order_id).first_or_404()
    business = Business.query.get(current_user.business_id)
    plan = SubscriptionPlan.query.get(payment.subscription_plan_id)

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, payment, business, plan]):
        flash('Invalid payment data. Please contact support.', 'danger')
        return redirect(url_for('billing.subscribe'))

    client = razorpay.Client(auth=(current_app.config['RAZORPAY_KEY_ID'], current_app.config['RAZORPAY_KEY_SECRET']))
    
    try:
        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }
        client.utility.verify_payment_signature(params_dict)
        
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.status = 'successful'
        
        business.subscription_status = 'active'
        business.subscription_plan_id = plan.id
        
        # If subscription is already active, extend it. Otherwise, start from today.
        start_date = datetime.utcnow()
        if business.subscription_ends_at and business.subscription_ends_at > start_date:
            start_date = business.subscription_ends_at
        
        business.subscription_ends_at = start_date + timedelta(days=plan.duration_days)
        
        db.session.commit()
        
        flash('Payment successful! Your subscription has been activated.', 'success')
        return redirect(url_for('manager.dashboard'))

    except Exception as e:
        payment.status = 'failed'
        db.session.commit()
        flash(f'Payment verification failed: {e}. Please contact support.', 'danger')
        return redirect(url_for('billing.subscribe'))