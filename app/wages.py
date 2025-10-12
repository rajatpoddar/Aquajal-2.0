# /water_supply_app/app/wages.py

from .models import User, DailyLog, Expense
from . import db
from datetime import date, datetime, time
from sqlalchemy import func

def deduct_daily_wages(app):
    """
    This function is called by the scheduler to deduct wages.
    It needs the app context to interact with the database.
    """
    with app.app_context():
        today = date.today()
        start_of_day = datetime.combine(today, time.min)
        end_of_day = datetime.combine(today, time.max)
        
        staff_members = User.query.filter_by(role='staff').all()
        
        print(f"--- [SCHEDULER] Running Wage Deduction for {today.isoformat()} ---")

        for staff in staff_members:
            if not staff.daily_wage or staff.daily_wage <= 0 or not staff.business:
                print(f"Skipping {staff.username}: No wage set or not assigned to a business.")
                continue

            jars_sold = db.session.query(func.sum(DailyLog.jars_delivered)).filter(
                DailyLog.user_id == staff.id,
                DailyLog.timestamp.between(start_of_day, end_of_day)
            ).scalar() or 0

            wage_to_deduct = 0
            attendance_status = "Absent"

            # Use the values from the business settings
            full_day_min = staff.business.full_day_jar_count
            half_day_min = staff.business.half_day_jar_count

            if jars_sold >= full_day_min:
                wage_to_deduct = staff.daily_wage
                attendance_status = "Full Day"
            elif jars_sold >= half_day_min:
                wage_to_deduct = staff.daily_wage / 2
                attendance_status = "Half Day"

            if wage_to_deduct > 0:
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
                print(f"No wage deducted for {staff.username} ({attendance_status}, {jars_sold} jars).")
        
        db.session.commit()
        print("--- [SCHEDULER] Wage deduction complete. ---")