from flask import render_template
from flask_mail import Message
from app import mail
from flask import current_app
from weasyprint import HTML, CSS
from .models import User  # Import the User model

def send_email(subject, sender, recipients, text_body, html_body, attachments=None):
    """General purpose email sending function."""
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    if attachments:
        for attachment in attachments:
            msg.attach(*attachment)
    mail.send(msg)

def send_password_reset_email(user):
    """Sends a password reset email to a user."""
    token = user.get_reset_password_token()
    send_email('[Aquajal] Reset Your Password',
               sender=current_app.config['ADMINS'][0],
               recipients=[user.email],
               text_body=render_template('email/reset_password.txt', user=user, token=token),
               html_body=render_template('email/reset_password.html', user=user, token=token))

def send_registration_email(user):
    """Sends a welcome email upon new business registration."""
    send_email('[Aquajal] Welcome to Aquajal!',
               sender=current_app.config['ADMINS'][0],
               recipients=[user.email],
               text_body=render_template('email/welcome.txt', user=user),
               html_body=render_template('email/welcome.html', user=user))

def send_invoice_email(invoice):
    """Generates a PDF invoice and emails it to the customer."""
    manager = User.query.filter_by(business_id=invoice.business_id, role='manager').first()
    html = render_template('invoices/invoice_template.html', invoice=invoice, manager=manager)
    pdf = HTML(string=html).write_pdf()
    
    send_email(f'[Aquajal] Invoice {invoice.invoice_number} from {invoice.customer.business.name}',
               sender=current_app.config['ADMINS'][0],
               recipients=[invoice.customer.email],
               text_body=render_template('email/invoice_email.txt', invoice=invoice),
               html_body=render_template('email/invoice_email.html', invoice=invoice),
               attachments=[(f'{invoice.invoice_number}.pdf', 'application/pdf', pdf)])

def send_jar_request_notification(customer, quantity, manager_email, staff_emails):
    """Notifies manager and staff about a new jar request from a customer."""
    recipients = [manager_email] + staff_emails
    send_email('[Aquajal] New Jar Request',
               sender=current_app.config['ADMINS'][0],
               recipients=recipients,
               text_body=f"A new jar request for {quantity} jar(s) from {customer.name}.",
               html_body=render_template('email/jar_request_notification.html', customer=customer, quantity=quantity))

def send_event_booking_notification(booking, manager_email, staff_emails):
    """Notifies manager and staff about a new event booking."""
    recipients = [manager_email] + staff_emails
    send_email('[Aquajal] New Event Booking for Confirmation',
               sender=current_app.config['ADMINS'][0],
               recipients=recipients,
               text_body=f"A new event booking from {booking.customer.name} requires confirmation.",
               html_body=render_template('email/event_booking_notification.html', booking=booking))

def send_booking_confirmed_email_to_staff(booking, staff_user):
    """Notifies an individual staff member that a manager has confirmed an event booking."""
    if staff_user.email:
        send_email(f'[Aquajal] Event Booking Confirmed for {booking.customer.name}',
                   sender=current_app.config['ADMINS'][0],
                   recipients=[staff_user.email],
                   text_body=f"An event booking for {booking.customer.name} on {booking.event_date} has been confirmed.",
                   html_body=render_template('email/booking_confirmed_staff.html', booking=booking, staff=staff_user))

def send_booking_confirmed_email_to_customer(booking):
    """Sends a booking confirmation email to the customer."""
    if booking.customer.email:
        send_email(f'[Aquajal] Your Event Booking with {booking.customer.business.name} is Confirmed!',
                   sender=current_app.config['ADMINS'][0],
                   recipients=[booking.customer.email],
                   text_body=f"Your booking for {booking.quantity} jars on {booking.event_date} is confirmed.",
                   html_body=render_template('email/booking_confirmed_customer.html', booking=booking))

def send_delivery_confirmation_email(customer, business, jars_delivered, amount, payment_status):
    """Sends a delivery confirmation email to the customer."""
    if customer.email:
        send_email(f'[Aquajal] Your Delivery from {business.name} is Complete',
                   sender=current_app.config['ADMINS'][0],
                   recipients=[customer.email],
                   text_body=f"Your delivery of {jars_delivered} jar(s) is complete.",
                   html_body=render_template('email/delivery_notification.html', customer=customer, business=business, jars_delivered=jars_delivered, amount=amount, payment_status=payment_status))

def send_order_status_update_email(order):
    """Sends an email to the manager when a supplier updates a purchase order status."""
    manager = User.query.filter_by(business_id=order.business_id, role='manager').first()
    if manager and manager.email:
        send_email(f'[Aquajal] Status Update for Order #{order.id}',
                   sender=current_app.config['ADMINS'][0],
                   recipients=[manager.email],
                   text_body=f"The status of your order #{order.id} has been updated to {order.status}.",
                   html_body=render_template('email/order_status_update.html', order=order, manager=manager))

def send_new_order_to_supplier_email(order):
    """Sends an email to the supplier about a new purchase order."""
    supplier_user = User.query.get(order.supplier.user_id)
    if supplier_user and supplier_user.email:
        send_email(f'[Aquajal] You Have a New Order (#{order.id}) from {order.business.name}',
                   sender=current_app.config['ADMINS'][0],
                   recipients=[supplier_user.email],
                   text_body=f"You have received a new order for a total of Rs. {order.total_amount}. Please log in to your supplier dashboard to view details and confirm.",
                   html_body=render_template('email/new_order_supplier.html', order=order))