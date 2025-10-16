import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-hard-to-guess-string'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- Email Server Configuration ---
    # Replace with your actual email server details.
    # For Gmail, you might need to generate an "App Password".
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'your-email@gmail.com') # <-- IMPORTANT: REPLACE
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'your-app-password')   # <-- IMPORTANT: REPLACE
    ADMINS = [os.environ.get('ADMINS', 'your-email@gmail.com')] # <-- IMPORTANT: REPLACE
    # ------------------------------------
    
    # --- Other Configurations ---
    UPLOAD_FOLDER = os.path.join(basedir, 'app/static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    
    # --- Razorpay API Keys ---
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

    # --- Babel (Internationalization) ---
    LANGUAGES = {
        'en': 'English',
        'hi': 'हिंदी',    # Hindi
        'bn': 'বাংলা',   # Bengali
        'mr': 'मराठी',  # Marathi
        'te': 'తెలుగు',   # Telugu
        'ta': 'தமிழ்',    # Tamil
        'gu': 'ગુજરાતી', # Gujarati
        'pa': 'ਪੰਜਾਬੀ'  # Punjabi
    }

    @staticmethod
    def init_app(app):
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])