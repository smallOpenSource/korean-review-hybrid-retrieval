"""
App Reviews Analysis System - Flask Application Factory.

This module initializes the Flask application with all required
configurations, extensions, and blueprints.
"""

import os
import logging
import structlog
from flask import Flask, jsonify
from pathlib import Path
from datetime import timedelta
from flask_jwt_extended import JWTManager

from app.config.settings import get_settings


def configure_logging(app: Flask):
    """Configure structured logging for the application."""
    settings = get_settings()

    # Ensure log directory exists
    log_path = Path(settings.logging.file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure structlog for JSON logging
    if settings.logging.format == 'json':
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    # Configure standard logging
    log_level = getattr(logging, settings.logging.level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(settings.logging.file_path),
            logging.StreamHandler()
        ]
    )

    app.logger.setLevel(log_level)
    app.logger.info(f"Logging configured: level={settings.logging.level}, file={settings.logging.file_path}")


def register_blueprints(app: Flask):
    """Register all Flask blueprints."""
    # Register Blueprints
    from app.views import views_bp, settings
    app.register_blueprint(views_bp)
    app.register_blueprint(settings.bp)

    # Register API Blueprints
    from app.api.v1 import api_bp
    from app.api.v1.auth import auth_bp
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    app.register_blueprint(auth_bp)

    app.logger.info("Blueprints registered")


def initialize_extensions(app: Flask):
    """Initialize Flask extensions and connections."""
    # Connections are lazy-loaded, but we can verify them here
    settings = get_settings()

    # JWT Configuration (MUST be set before JWTManager initialization)
    app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY') or app.config.get('SECRET_KEY')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(
        seconds=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))
    )
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(
        seconds=int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))
    )

    # Initialize JWT Manager (after config is set)
    jwt = JWTManager(app)

    # JWT Error Handlers
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        return jsonify({
            'status': 'error',
            'error_code': 'UNAUTHORIZED',
            'message': 'Missing or invalid authentication token'
        }), 401

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({
            'status': 'error',
            'error_code': 'TOKEN_EXPIRED',
            'message': 'Authentication token has expired'
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({
            'status': 'error',
            'error_code': 'INVALID_TOKEN',
            'message': 'Invalid authentication token'
        }), 401

    app.logger.info(f"Application: {settings.app.name} v{settings.app.version}")
    app.logger.info(f"Environment: {settings.flask.env}")
    app.logger.info("JWT Manager initialized")
    
    # Register context processor for global template variables
    @app.context_processor
    def inject_complaint_count():
        """Inject pending complaints count to all templates."""
        try:
            from app.services.review_service import get_review_service
            service = get_review_service()
            stats = service.get_complaint_stats_sync(days=3650)  # All time complaints
            
            pending_count = 0
            for bucket in stats.get('status_breakdown', []):
                if bucket['key'] in ['new', 'in_progress', 'escalated']:
                    pending_count += bucket['doc_count']
            
            return {'pending_complaints_count': pending_count}
        except Exception as e:
            app.logger.error(f"Error getting complaint count: {e}")
            return {'pending_complaints_count': 0}


def create_app(config_override: dict = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config_override: Optional configuration overrides for testing

    Returns:
        Configured Flask application
    """
    settings = get_settings()

    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static'
    )

    # Flask configuration
    app.config['SECRET_KEY'] = settings.flask.secret_key
    app.config['DEBUG'] = settings.flask.debug
    app.config['JSON_AS_ASCII'] = False  # Support Korean in JSON responses

    # Apply any config overrides
    if config_override:
        app.config.update(config_override)

    # No built-in fallback secret: refuse to start without one.
    if not app.config.get('SECRET_KEY'):
        raise RuntimeError(
            "SECRET_KEY is not set. Define SECRET_KEY (and optionally JWT_SECRET_KEY) "
            "in the environment or .env file before starting the app."
        )

    # Initialize components
    configure_logging(app)
    initialize_extensions(app)
    register_blueprints(app)

    # Global Error Handlers
    from app.utils.errors import APIError
    from werkzeug.exceptions import HTTPException
    import traceback

    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        """Handle custom API errors"""
        app.logger.error(
            "API error occurred",
            extra={
                'error_code': error.error_code,
                'status_code': error.status_code,
                'error_message': error.message,
                'details': error.details
            }
        )
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        """Handle Werkzeug HTTP exceptions"""
        app.logger.warning(
            f"HTTP exception: {error.code} - {error.description}"
        )
        return jsonify({
            'status': 'error',
            'error_code': 'HTTP_ERROR',
            'message': error.description
        }), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        """Catch-all for unexpected errors"""
        app.logger.error(
            "Unexpected error occurred",
            extra={
                'error_type': type(error).__name__,
                'error_message': str(error),
                'traceback': traceback.format_exc()
            }
        )
        return jsonify({
            'status': 'error',
            'error_code': 'INTERNAL_SERVER_ERROR',
            'message': 'An unexpected error occurred. Please contact support if the problem persists.'
        }), 500

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'status': 'error',
            'error_code': 'NOT_FOUND',
            'message': 'The requested endpoint does not exist'
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            'status': 'error',
            'error_code': 'METHOD_NOT_ALLOWED',
            'message': 'The method is not allowed for this endpoint'
        }), 405

    # Health check endpoint
    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'version': settings.app.version}

    app.logger.info("Application created successfully")
    app.logger.info("Global error handlers registered")

    # Register context processors
    from app.constants.mappings import SENTIMENT_LABELS, COMPLAINT_TYPES, DEPARTMENTS, CATEGORIES, URGENCY_LEVELS, STATUS_LABELS
    
    @app.context_processor
    def inject_mappings():
        return dict(
            SENTIMENT_LABELS=SENTIMENT_LABELS,
            COMPLAINT_TYPES=COMPLAINT_TYPES,
            DEPARTMENTS=DEPARTMENTS,
            CATEGORIES=CATEGORIES,
            URGENCY_LEVELS=URGENCY_LEVELS,
            STATUS_LABELS=STATUS_LABELS
        )

    return app
