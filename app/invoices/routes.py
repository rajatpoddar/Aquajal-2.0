from flask import render_template, flash, redirect, url_for, request, Response, abort
from flask_login import login_required, current_user
from app import db
from app.invoices import bp
from app.models import Invoice, Customer, InvoiceItem, EventBooking, DailyLog
from weasyprint import HTML, CSS
from app.email import send_invoice_email
from app.decorators import manager_required
from datetime import date, timedelta

# --- HELPER FUNCTIONS ---
def generate_new_invoice_number(business_id):
    # This generates a unique invoice number for the business
    last_invoice_num = Invoice.query.filter_by(business_id=business_id).count()
    return f"AQUA-{business_id}-{date.today().year}-{last_invoice_num + 1:04d}"

def create_invoice_for_transaction(customer, business, items, issue_date=None):
    if not issue_date:
        issue_date = date.today()

    total_amount = sum(item['total'] for item in items)
    if total_amount <= 0:
        return None # Don't create an invoice for zero-amount transactions

    new_invoice = Invoice(
        invoice_number=generate_new_invoice_number(business.id),
        issue_date=issue_date,
        due_date=issue_date + timedelta(days=15),
        total_amount=total_amount,
        customer_id=customer.id,
        business_id=business.id
    )
    db.session.add(new_invoice)

    for item_data in items:
        item = InvoiceItem(
            description=item_data['description'],
            quantity=item_data['quantity'],
            unit_price=item_data['unit_price'],
            total=item_data['total']
        )
        new_invoice.items.append(item)
    
    db.session.commit()
    return new_invoice

# Route to view a single invoice as HTML
@bp.route('/view/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    # Security check
    if isinstance(current_user, Customer) and invoice.customer_id != current_user.id:
        abort(403)
    if current_user.role == 'manager' and invoice.business_id != current_user.business_id:
        abort(403)
        
    return render_template('invoices/invoice_template.html', invoice=invoice)

# Route to download an invoice as PDF
@bp.route('/download/<int:invoice_id>')
@login_required
def download_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    # Security check
    if isinstance(current_user, Customer) and invoice.customer_id != current_user.id:
        abort(403)
    if current_user.role == 'manager' and invoice.business_id != current_user.business_id:
        abort(403)

    html = render_template('invoices/invoice_template.html', invoice=invoice)
    pdf = HTML(string=html).write_pdf()
    
    return Response(pdf,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment;filename={invoice.invoice_number}.pdf'})

# Route for manager to email an invoice
@bp.route('/email/<int:invoice_id>')
@login_required
def email_invoice(invoice_id):
    if current_user.role != 'manager':
        abort(403)
    
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.business_id != current_user.business_id:
        abort(403)
    
    if not invoice.customer.email:
        flash('Cannot send email. This customer does not have an email address on file.', 'danger')
        return redirect(url_for('invoices.list_invoices'))

    send_invoice_email(invoice)
    flash(f'Invoice {invoice.invoice_number} has been sent to {invoice.customer.name}.', 'success')
    return redirect(url_for('invoices.list_invoices'))

# Route to list all invoices for the manager
@bp.route('/list')
@login_required
@manager_required
def list_invoices():
    page = request.args.get('page', 1, type=int)
    invoices = Invoice.query.filter_by(business_id=current_user.business_id).order_by(Invoice.issue_date.desc()).paginate(page=page, per_page=10)
    return render_template('manager/list_invoices.html', invoices=invoices, title="All Invoices")

@bp.route('/generate/<int:customer_id>', methods=['GET', 'POST'])
@login_required
@manager_required
def generate_invoice(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == 'POST':
        month = int(request.form['month'])
        year = int(request.form['year'])
        
        start_date = date(year, month, 1)
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        
        total_amount = 0
        invoice_items = []
        
        # 1. Daily Jar Deliveries
        daily_logs = DailyLog.query.filter(
            DailyLog.customer_id == customer.id,
            DailyLog.timestamp >= start_date,
            DailyLog.timestamp <= end_date
        ).all()
        
        if daily_logs:
            total_jars = sum(log.jars_delivered for log in daily_logs)
            avg_price = sum(log.amount_collected for log in daily_logs) / total_jars if total_jars > 0 else customer.price_per_jar
            item_total = total_jars * avg_price
            invoice_items.append(InvoiceItem(description=f"Monthly Jar Supply ({start_date.strftime('%b %Y')})", quantity=total_jars, unit_price=avg_price, total=item_total))
            total_amount += item_total

        # 2. Event Bookings
        event_bookings = EventBooking.query.filter(
            EventBooking.customer_id == customer.id,
            EventBooking.status == 'Completed',
            EventBooking.collection_timestamp >= start_date,
            EventBooking.collection_timestamp <= end_date
        ).all()

        for booking in event_bookings:
            invoice_items.append(InvoiceItem(description=f"Event Booking on {booking.event_date.strftime('%d-%b')}", quantity=1, unit_price=booking.final_amount, total=booking.final_amount))
            total_amount += booking.final_amount

        if not invoice_items:
            flash('No billable activity found for this customer in the selected month.', 'warning')
            return redirect(url_for('invoices.generate_invoice', customer_id=customer_id))

        last_invoice_num = Invoice.query.filter_by(business_id=current_user.business_id).count()
        new_invoice_number = f"AQUA-{current_user.business_id}-{date.today().year}-{last_invoice_num + 1:04d}"

        new_invoice = Invoice(
            invoice_number=new_invoice_number,
            due_date=date.today() + timedelta(days=15),
            total_amount=total_amount,
            customer_id=customer.id,
            business_id=current_user.business_id
        )
        db.session.add(new_invoice)
        
        for item in invoice_items:
            new_invoice.items.append(item)
            
        db.session.commit()
        flash(f'Invoice {new_invoice_number} generated successfully!', 'success')
        return redirect(url_for('invoices.list_invoices'))

    return render_template('manager/generate_invoice_form.html', customer=customer, title="Generate Invoice")