from flask import Blueprint

bp = Blueprint('push_notifications', __name__)

from app.push_notifications import routes
