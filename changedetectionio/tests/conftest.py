#!/usr/bin/env python3
import psutil
import time
from threading import Thread
import multiprocessing

import pytest
import arrow
from changedetectionio import store
import os
import sys

# CRITICAL: Set short timeout for tests to prevent 45-second hangs
# When test server is slow/unresponsive, workers fail fast instead of holding UUIDs for 45s
# This prevents exponential priority growth from repeated deferrals (priority × 10 each defer)
os.environ['DEFAULT_SETTINGS_REQUESTS_TIMEOUT'] = '5'
# Test server runs on localhost (127.0.0.1) which is a private IP.
# Allow it globally so all existing tests keep working; test_ssrf_protection
# uses monkeypatch to temporarily override this for its own assertions.
os.environ['ALLOW_IANA_RESTRICTED_ADDRESSES'] = 'true'

from changedetectionio.flask_app import init_app_secret, changedetection_app
from changedetectionio.tests.util import live_server_setup, new_live_server_setup

# https://github.com/pallets/flask/blob/1.1.2/examples/tutorial/tests/test_auth.py
# Much better boilerplate than the docs
# https://www.python-boilerplate.com/py3+flask+pytest/

global app

# https://loguru.readthedocs.io/en/latest/resources/migration.html#replacing-caplog-fixture-from-pytest-library
# Show loguru logs only if CICD pytest fails.
from loguru import logger
@pytest.fixture
def reportlog(pytestconfig):
    logging_plugin = pytestconfig.pluginmanager.getplugin("logging-plugin")
    handler_id = logger.add(logging_plugin.report_handler, format="{message}")
    yield
    logger.remove(handler_id)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to capture test results and attach to the test node."""
    outcome = yield
    rep = outcome.get_result()

    # Store report on the test node for access in fixtures
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture
def environment(mocker):
    """Mock arrow.now() to return a fixed datetime for testing jinja2 time extension."""
    # Fixed datetime: Wed, 09 Dec 2015 23:33:01 UTC
    # This is calculated to match the test expectations when offsets are applied
    fixed_datetime = arrow.Arrow(2015, 12, 9, 23, 33, 1, tzinfo='UTC')
    # Patch on the arrow module itself - TimeExtension imports arrow lazily inside its methods
    # (import diet), so there is no module-level TimeExtension.arrow attribute to patch
    mocker.patch('arrow.now', return_value=fixed_datetime)
    return fixed_datetime


