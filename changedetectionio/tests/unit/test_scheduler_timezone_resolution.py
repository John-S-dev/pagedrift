#!/usr/bin/env python3

"""
Regression tests for the scheduler's default-timezone resolution.

The bug: model/App.py initialises 'scheduler_timezone_default' to None, so the
key ALWAYS EXISTS with a None value. Call sites used

    settings['application'].get('scheduler_timezone_default', os.getenv('TZ', 'UTC'))

which never reaches its fallback, because dict.get() only substitutes the
default when the key is ABSENT - not when its value is None. The resulting None
flowed into is_within_schedule(), which does `tz_name.strip()` and raised
AttributeError. That took out the edit page (HTTP 500) and, worse, the ticker
thread (which did `return False` inside its main loop and stopped scheduling
every watch until restart).

Run:  python3 -m unittest changedetectionio.tests.unit.test_scheduler_timezone_resolution
"""

import os
import unittest
from unittest.mock import patch

