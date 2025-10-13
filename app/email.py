from flask import render_template
from flask_mail import Message
from app import mail
from flask import current_app
from weasyprint import HTML, CSS

def send_email(subject, sender, recipients, text_body, html_body, attachments=None):
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    if attachments:
        for attachment in attachments:
            msg.attach(*attachment)
    mail.send(msg)

def send_password_reset_email(user):
    token = user.get_reset_password_token()
    send_email('[Aquajal] Reset Your Password',
               sender=current_app.config['ADMINS'][0],
               recipients=[user.email],
               text_body=render_template('email/reset_password.txt',
                                         user=user, token=token),
               html_body=render_template('email/reset_password.html',
                                         user=user, token=token))

def send_registration_email(user):
    send_email('[Aquajal] Welcome to Aquajal!',
               sender=current_app.config['ADMINS'][0],
               recipients=[user.email],
               text_body=render_template('email/welcome.txt', user=user),
               html_body=render_template('email/welcome.html', user=user))
    
def send_invoice_email(invoice):
    html = render_template('invoices/invoice_template.html', invoice=invoice)
    pdf = HTML(string=html).write_pdf()
    
    send_email(f'[Aquajal] Invoice {invoice.invoice_number} from {invoice.customer.business.name}',
               sender=current_app.config['ADMINS'][0],
               recipients=[invoice.customer.email],
               text_body=f"Dear {invoice.customer.name},\n\nPlease find attached your invoice ({invoice.invoice_number}).\n\nTotal Amount Due: ₹{invoice.total_amount:.2f}\n\nThank you!",
               html_body=render_template('email/invoice_email.html', invoice=invoice),
               attachments=[(f'{invoice.invoice_number}.pdf', 'application/pdf', pdf)])