from flask import render_template
from app import db
from app.errors import bp

# Custom handler for 404 Not Found errors
@bp.app_errorhandler(404)
def not_found_error(error):
    """
    Renders the custom 404 error page.
    """
    return render_template('errors/404.html'), 404

# Custom handler for 500 Internal Server errors
@bp.app_errorhandler(500)
def internal_error(error):
    """
    Rolls back the database session and renders the custom 500 error page.
    """
    db.session.rollback()
    return render_template('errors/500.html'), 500
