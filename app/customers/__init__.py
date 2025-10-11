# /water_supply_app/app/customers/__init__.py

from flask import Blueprint

bp = Blueprint('customers', __name__)

from app.customers import routes