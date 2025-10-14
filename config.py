# File: config.py
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key'

    # --- Database Configuration ---
    # Attempt to load PostgreSQL credentials from environment variables
    POSTGRES_USER = os.environ.get('POSTGRES_USER')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD')
    POSTGRES_HOSTNAME = os.environ.get('POSTGRES_HOSTNAME', 'db') # 'db' is the service name in docker-compose
    POSTGRES_DB = os.environ.get('POSTGRES_DB')

    # If PostgreSQL credentials are provided, use them. Otherwise, fall back to SQLite.
    if all([POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOSTNAME, POSTGRES_DB]):
        SQLALCHEMY_DATABASE_URI = (
            f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
            f"{POSTGRES_HOSTNAME}/{POSTGRES_DB}"
        )
    else:
        # Fallback to your original SQLite configuration
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
            'sqlite:///' + os.path.join(basedir, 'app.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- THIS LINE WAS MISSING AND IS NOW RESTORED ---
    UPLOAD_FOLDER = os.path.join(basedir, 'app/static/uploads')
    
    # --- Razorpay API Keys ---
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')

    # --- Email Configuration ---
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    ADMINS = ['your-email@example.com']
    
    # --- Supported languages (Preserved from your original file) ---
    LANGUAGES = {
        'en': 'English',
        'hi': 'हिन्दी',       # Hindi
        'bn': 'বাংলা',       # Bengali
        'mr': 'मराठी',      # Marathi
        'pa': 'ਪੰਜਾਬੀ',     # Punjabi
        'ta': 'தமிழ்',      # Tamil
        'te': 'తెలుగు',     # Telugu
        'gu': 'ગુજરાતી'      # Gujarati
    }