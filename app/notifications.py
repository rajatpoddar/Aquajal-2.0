# File: app/notifications.py
from flask import current_app, url_for
from app.models import PushSubscription, User, Customer
from app import db
from pywebpush import webpush, WebPushException
import json

def send_push_notification(user_or_customer, title, body):
    # Determine if the recipient is a User (employee) or a Customer
    if isinstance(user_or_customer, User):
        subscriptions = PushSubscription.query.filter_by(user_id=user_or_customer.id).all()
    elif isinstance(user_or_customer, Customer):
        subscriptions = PushSubscription.query.filter_by(customer_id=user_or_customer.id).all()
    else:
        return # Not a valid recipient type

    if not subscriptions:
        return

    vapid_private_key = current_app.config['VAPID_PRIVATE_KEY']
    vapid_claims = {"sub": f"mailto:{current_app.config['VAPID_ADMIN_EMAIL']}"}

    for sub in subscriptions:
        try:
            webpush(
                subscription_info=json.loads(sub.subscription_json),
                data=json.dumps({'title': title, 'body': body}),
                vapid_private_key=vapid_private_key,
                vapid_claims=vapid_claims
            )
        except WebPushException as ex:
            # If a subscription is expired or invalid, delete it from the DB
            if ex.response.status_code == 410:
                db.session.delete(sub)
                db.session.commit()
            else:
                print(f"Error sending push notification: {ex}")
