"""
Views module for HTML page rendering.
"""

from flask import Blueprint

views_bp = Blueprint('views', __name__)

# Import routes to register them
from . import dashboard, company, complaints
