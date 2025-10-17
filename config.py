import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-hard-to-guess-string'
    
    # --- DATABASE CONFIGURATION ---
    # Updated logic to prioritize PostgreSQL in a Docker environment
    if os.environ.get('POSTGRES_HOSTNAME'):
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql://{os.environ.get('POSTGRES_USER')}:"
            f"{os.environ.get('POSTGRES_PASSWORD')}@"
            f"{os.environ.get('POSTGRES_HOSTNAME')}:5432/"
            f"{os.environ.get('POSTGRES_DB')}"
        )
    else:
        # Fallback to DATABASE_URL or a local SQLite database for development
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
            'sqlite:///' + os.path.join(basedir, 'app.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- Email Server Configuration ---
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.googlemail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    ADMINS = [os.environ.get('ADMINS', 'your-email@gmail.com')]
    
    # --- Other Configurations ---
    UPLOAD_FOLDER = os.path.join(basedir, 'app/static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    
    # --- Razorpay API Keys ---
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

    # --- VAPID Keys for Push Notifications ---
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_ADMIN_EMAIL = os.environ.get('VAPID_ADMIN_EMAIL')

    # --- Babel (Internationalization) ---
    LANGUAGES = {
        'en': 'English',
        'hi': 'हिंदी',
        'bn': 'বাংলা',
        'mr': 'मराठी',
        'te': 'తెలుగు',
        'ta': 'தமிழ்',
        'gu': 'ગુજરાતી',
        'pa': 'ਪੰਜਾਬੀ'
    }

    @staticmethod
    def init_app(app):
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])