from flask import request, jsonify, current_app
from flask_login import current_user, login_required
from app import db
from app.push_notifications import bp
from app.models import PushSubscription, User, Customer
import json

@bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    subscription_data = request.get_json()
    if not subscription_data:
        return jsonify({'error': 'No subscription data provided'}), 400

    subscription_json = json.dumps(subscription_data)

    # Check if this subscription already exists for this user
    existing_sub = None
    if isinstance(current_user, User):
        existing_sub = PushSubscription.query.filter_by(user_id=current_user.id, subscription_json=subscription_json).first()
    elif isinstance(current_user, Customer):
         existing_sub = PushSubscription.query.filter_by(customer_id=current_user.id, subscription_json=subscription_json).first()

    if existing_sub:
        return jsonify({'message': 'Subscription already exists'}), 200

    # Create new subscription
    new_sub = PushSubscription(subscription_json=subscription_json)
    if isinstance(current_user, User):
        new_sub.user_id = current_user.id
    elif isinstance(current_user, Customer):
        new_sub.customer_id = current_user.id

    db.session.add(new_sub)
    db.session.commit()

    return jsonify({'message': 'Subscription successful'}), 201
