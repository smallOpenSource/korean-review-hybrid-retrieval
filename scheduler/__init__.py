"""
Scheduler package for Korean Financial App Review Collection and Analysis.

This is a separated scheduler service that runs independently from the main Flask app.
It handles:
- Periodic review collection from Google Play Store
- Review analysis using the main app's API
- Word cloud generation
- Data cleanup and optimization
"""

__version__ = "1.0.0"
