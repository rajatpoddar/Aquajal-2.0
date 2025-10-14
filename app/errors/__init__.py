from flask import Blueprint

# Create a new Blueprint for error handlers
bp = Blueprint('errors', __name__)

# Import the handlers to link them to the blueprint
from app.errors import handlers
