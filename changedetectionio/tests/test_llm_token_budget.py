#!/usr/bin/env python3
"""
Tests that verify global LLM token budget counters cannot be tampered with
via the API (watch PUT) or via form submissions (settings page POST).

import pytest
from flask import url_for

from changedetectionio.tests.util import live_server_setup, delete_all_watches


