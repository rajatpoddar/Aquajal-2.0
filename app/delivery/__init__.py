# /water_supply_app/app/delivery/__init__.py

from flask import Blueprint

bp = Blueprint('delivery', __name__)

from app.delivery import routes