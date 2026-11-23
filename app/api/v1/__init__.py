"""
API v1 Blueprint registration.
"""

from flask import Blueprint

api_bp = Blueprint('api_v1', __name__)

# Import routes to register them
from . import reviews, analysis, complaints, search, dashboard
