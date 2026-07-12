#!/usr/bin/env python3
"""
Tests for immediate commit-based persistence system.

Tests cover:
- Watch.commit() persistence to disk
- Concurrent commit safety (race conditions)
- Processor config separation
- Data loss prevention (settings, tags, watch modifications)
"""

import json
import os
import threading
import time
from flask import url_for
from .util import wait_for_all_checks


