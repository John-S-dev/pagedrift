"""
Watch domain model for change detection monitoring.

ARCHITECTURE NOTE: Configuration Override Hierarchy
===================================================

1. CHAIN RESOLUTION (Watch → Tag → Global Settings)
   - Current: Manual resolution scattered across codebase
   - Future: @computed_field properties with automatic resolution
   - Examples: resolved_fetch_backend, resolved_restock_settings, etc.

2. DATABASE BACKEND ABSTRACTION
   - Current: Domain model tightly coupled to file-based JSON storage
   - Future: Domain model (Pydantic) separate from persistence layer
   - Enables: Easy migration to PostgreSQL, MongoDB, etc.

3. TYPE SAFETY & VALIDATION
   - Current: Dict access with no compile-time checks
   - Future: Type hints, IDE autocomplete, validation at boundaries

See class model docstring for detailed explanation and examples.
See: processors/restock_diff/processor.py:184-192 for manual resolution example
"""

from blinker import signal
from changedetectionio.validate_url import is_safe_valid_url

from changedetectionio.strtobool import strtobool
from changedetectionio.jinja2_custom import render as jinja_render
from . import watch_base
from .persistence import EntityPersistenceMixin
import os
import re
from pathlib import Path
from loguru import logger

minimum_seconds_recheck_time = int(os.getenv('MINIMUM_SECONDS_RECHECK_TIME', 3))
mtable = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400, 'weeks': 86400 * 7}

