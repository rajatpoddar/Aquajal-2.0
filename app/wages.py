# /water_supply_app/app/wages.py

from .models import User, DailyLog, Expense, Business # Import Business
from . import db
from datetime import date, datetime, time
from sqlalchemy import func

def deduct_daily_wages(app):
    """
    This function is called by the scheduler to deduct daily wages.
    It only processes staff members marked with 'daily' wage_type.
    It needs the app context to interact with the database.
    """
    with app.app_context():
        today = date.today()
        start_of_day = datetime.combine(today, time.min)
        end_of_day = datetime.combine(today, time.max)
        
        # Filter for staff who are on daily wages
        staff_members = User.query.filter_by(role='staff', wage_type='daily').all()
        
        print(f"--- [SCHEDULER] Running Daily Wage Deduction for {today.isoformat()} ---")

        for staff in staff_members:
            # Ensure staff has a daily wage set and belongs to a business with settings
            if not staff.daily_wage or staff.daily_wage <= 0 or not staff.business:
                print(f"Skipping {staff.username}: No daily wage set or not assigned to a business with attendance rules.")
                continue

            business_settings = staff.business # Get the business object

            # Fetch jar counts from the associated business settings
            full_day_min = business_settings.full_day_jar_count
            half_day_min = business_settings.half_day_jar_count

            # If thresholds are not set in business, skip calculation for this staff
            if full_day_min is None or half_day_min is None:
                 print(f"Skipping {staff.username}: Business attendance thresholds not set.")
                 continue

            
            jars_sold = db.session.query(func.sum(DailyLog.jars_delivered)).filter(
                DailyLog.user_id == staff.id,
                DailyLog.timestamp.between(start_of_day, end_of_day)
            ).scalar() or 0

            wage_to_deduct = 0
            attendance_status = "Absent"

            if jars_sold >= full_day_min:
                wage_to_deduct = staff.daily_wage
                attendance_status = "Full Day"
            elif jars_sold >= half_day_min:
                wage_to_deduct = staff.daily_wage / 2
                attendance_status = "Half Day"

            if wage_to_deduct > 0:
                # Ensure cash balance is not None before deducting
                if staff.cash_balance is None:
                    staff.cash_balance = 0.0
                staff.cash_balance -= wage_to_deduct
                
                wage_expense = Expense(
                    amount=wage_to_deduct,
                    description=f"Daily Wage ({attendance_status})",
                    user_id=staff.id,
                    timestamp=datetime.utcnow()
                )
                db.session.add(wage_expense)
                print(f"Deducted ₹{wage_to_deduct:.2f} from {staff.username} ({attendance_status}, {jars_sold} jars).")
            else:
                print(f"No daily wage deducted for {staff.username} ({attendance_status}, {jars_sold} jars).")
        
        try:
            db.session.commit()
        except Exception as e:
             db.session.rollback()
             print(f"Error during wage deduction commit: {e}") # Log error

        print("--- [SCHEDULER] Daily Wage deduction complete. ---")