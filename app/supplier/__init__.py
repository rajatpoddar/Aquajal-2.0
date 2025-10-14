# File: app/supplier/__init__.py
from flask import Blueprint

bp = Blueprint('supplier', __name__)

# This line must be at the end
from app.supplier import routes