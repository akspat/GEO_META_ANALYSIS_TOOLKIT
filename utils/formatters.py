"""
utils/formatters.py — Output formatting for the GEO Meta-Analysis Toolkit.

Converts raw analysis results into display-ready structures.
"""

import json
from typing import Any


def pretty_json(obj: Any) -> str:
    """Pretty-print any object as JSON string."""
    return json.dumps(obj, indent=2, default=str)
