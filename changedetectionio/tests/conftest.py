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


@pytest.fixture(autouse=True)
def per_test_log_file(request):
    """Create a separate log file for each test function with pytest output."""
    import re

    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    # Generate log filename from test name and worker ID (for parallel runs)
    test_name = request.node.name

    # Sanitize test name - replace unsafe characters with underscores
    # Keep only alphanumeric, dash, underscore, and period
    safe_test_name = re.sub(r'[^\w\-.]', '_', test_name)

    # Limit length to avoid filesystem issues (max 200 chars)
    if len(safe_test_name) > 200:
        # Keep first 150 chars + hash of full name + last 30 chars
        import hashlib
        name_hash = hashlib.md5(test_name.encode()).hexdigest()[:8]
        safe_test_name = f"{safe_test_name[:150]}_{name_hash}_{safe_test_name[-30:]}"

    worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
    log_file = os.path.join(log_dir, f"{safe_test_name}_{worker_id}.log")

    # Add file handler for this test with TRACE level
    handler_id = logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process} | {name}:{function}:{line} - {message}",
        level="TRACE",
        mode="w",  # Overwrite if exists
        enqueue=True  # Thread-safe
    )

    logger.info(f"=== Starting test: {test_name} (worker: {worker_id}) ===")
    logger.info(f"Test location: {request.node.nodeid}")

    yield

    # Capture test outcome (PASSED/FAILED/SKIPPED/ERROR)
    outcome = "UNKNOWN"
    exc_info = None
    stdout = None
    stderr = None

    if hasattr(request.node, 'rep_call'):
        outcome = request.node.rep_call.outcome.upper()
        if request.node.rep_call.failed:
            exc_info = request.node.rep_call.longreprtext
        # Capture stdout/stderr from call phase
        if hasattr(request.node.rep_call, 'sections'):
            for section_name, section_content in request.node.rep_call.sections:
                if 'stdout' in section_name.lower():
                    stdout = section_content
                elif 'stderr' in section_name.lower():
                    stderr = section_content
    elif hasattr(request.node, 'rep_setup'):
        if request.node.rep_setup.failed:
            outcome = "SETUP_FAILED"
            exc_info = request.node.rep_setup.longreprtext

    logger.info(f"=== Test Result: {outcome} ===")

    if exc_info:
        logger.error(f"=== Test Failure Details ===\n{exc_info}")

    if stdout:
        logger.info(f"=== Captured stdout ===\n{stdout}")

    if stderr:
        logger.warning(f"=== Captured stderr ===\n{stderr}")

    logger.info(f"=== Finished test: {test_name} ===")
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


def format_memory_human(bytes_value):
    """Format memory in human-readable units (KB, MB, GB)"""
    if bytes_value < 1024:
        return f"{bytes_value} B"
    elif bytes_value < 1024 ** 2:
        return f"{bytes_value / 1024:.2f} KB"
    elif bytes_value < 1024 ** 3:
        return f"{bytes_value / (1024 ** 2):.2f} MB"
    else:
        return f"{bytes_value / (1024 ** 3):.2f} GB"

def track_memory(memory_usage, ):
    process = psutil.Process(os.getpid())
    while not memory_usage["stop"]:
        current_rss = process.memory_info().rss
        memory_usage["peak"] = max(memory_usage["peak"], current_rss)
        memory_usage["current"] = current_rss  # Keep updating current
        time.sleep(0.01)  # Adjust the sleep time as needed

@pytest.fixture(scope='function')
def measure_memory_usage(request):
    memory_usage = {"peak": 0, "current": 0, "stop": False}
    tracker_thread = Thread(target=track_memory, args=(memory_usage,))
    tracker_thread.start()

    yield

    memory_usage["stop"] = True
    tracker_thread.join()

    # Note: psutil returns RSS memory in bytes
    peak_human = format_memory_human(memory_usage["peak"])

    s = f"{time.time()} {request.node.fspath} - '{request.node.name}' - Peak memory: {peak_human}"
    logger.debug(s)

    with open("test-memory.log", 'a') as f:
        f.write(f"{s}\n")

    # Assert that the memory usage is less than 200MB
#    assert peak_memory_kb < 150 * 1024, f"Memory usage exceeded 150MB: {peak_human}"


def cleanup(datastore_path):
    import glob
    # Unlink test output files
    for g in ["*.txt", "*.json", "*.pdf"]:
        files = glob.glob(os.path.join(datastore_path, g))
        for f in files:
            if 'proxies.json' in f:
                # Usually mounted by docker container during test time
                continue
            if os.path.isfile(f):
                os.unlink(f)

def pytest_configure(config):
    """Configure pytest environment before tests run.

    CRITICAL: Set multiprocessing start method to 'fork' for Python 3.14+ compatibility.

    Python 3.14 changed the default start method from 'fork' to 'forkserver' on Linux.
    The forkserver method requires all objects to be picklable, but pytest-flask's
    LiveServer uses nested functions that can't be pickled.

    Setting 'fork' explicitly:
    - Maintains compatibility with Python 3.11-3.13 (where 'fork' was already default)
    - Fixes Python 3.14 pickling errors
    - Only affects Unix-like systems (Windows uses 'spawn' regardless)

    See: https://github.com/python/cpython/issues/126831
    See: https://docs.python.org/3/whatsnew/3.14.html
    """
    # Only set if not already set (respects existing configuration)
    if multiprocessing.get_start_method(allow_none=True) is None:
        try:
            # 'fork' is available on Unix-like systems (Linux, macOS)
            # On Windows, this will have no effect as 'spawn' is the only option
            multiprocessing.set_start_method('fork', force=False)
            logger.debug("Set multiprocessing start method to 'fork' for Python 3.14+ compatibility")
        except (ValueError, RuntimeError):
            # Already set, not available on this platform, or context already created
            pass

@pytest.fixture(scope='function', autouse=True)
def prepare_test_function(live_server, datastore_path):
    """Prepare each test with complete isolation.

    CRITICAL for xdist per-test isolation:
    - Reuses the SAME datastore instance (so blueprint references stay valid)
    - Clears all watches and state for a clean slate
    - First watch will get uuid="first"
    """
    routes = [rule.rule for rule in live_server.app.url_map.iter_rules()]
    if '/test-random-content-endpoint' not in routes:
        logger.debug("Setting up test URL routes")
        new_live_server_setup(live_server)

    # CRITICAL: Point app to THIS test's unique datastore directory
    live_server.app.config['TEST_DATASTORE_PATH'] = datastore_path

    # CRITICAL: Get datastore and stop it from writing stale data
    datastore = live_server.app.config.get('DATASTORE')

    # Clear the queue before starting the test to prevent state leakage
    from changedetectionio.flask_app import update_q
    while not update_q.empty():
        try:
            update_q.get_nowait()
        except:
            break

    # Add test helper methods to the app for worker management
    def set_workers(count):
        """Set the number of workers for testing - brutal shutdown, no delays"""
        from changedetectionio import worker_pool
        from changedetectionio.flask_app import update_q, notification_q

        current_count = worker_pool.get_worker_count()

       # Special case: Setting to 0 means shutdown all workers brutally
        if count == 0:
            logger.debug(f"Brutally shutting down all {current_count} workers")
            worker_pool.shutdown_workers()
            return {
                'status': 'success',
                'message': f'Shutdown all {current_count} workers',
                'previous_count': current_count,
                'current_count': 0
            }

        # Adjust worker count (no delays, no verification)
        result = worker_pool.adjust_async_worker_count(
            count,
            update_q=update_q,
            notification_q=notification_q,
            app=live_server.app,
            datastore=datastore
        )

        return result

    def check_all_workers_alive(expected_count):
        """Check that all expected workers are alive"""
        from changedetectionio import worker_pool
        from changedetectionio.flask_app import update_q, notification_q
        result = worker_pool.check_worker_health(
            expected_count,
            update_q=update_q,
            notification_q=notification_q,
            app=live_server.app,
            datastore=datastore
        )
        assert result['status'] == 'healthy', f"Workers not healthy: {result['message']}"
        return result

    # Attach helper methods to app for easy test access
    live_server.app.set_workers = set_workers
    live_server.app.check_all_workers_alive = check_all_workers_alive




    # CRITICAL: Clean up any files from previous tests
    # This ensures a completely clean directory
    cleanup(datastore_path)

    # CRITICAL: Reload the EXISTING datastore instead of creating a new one
    # This keeps blueprint references valid (they capture datastore at construction)
    # reload_state() completely resets the datastore to a clean state

    # Reload state with clean data (no default watches)
    datastore.reload_state(
        datastore_path=datastore_path,
        include_default_watches=False,
        version_tag=datastore.data.get('version_tag', '0.0.0')
    )
    live_server.app.secret_key = init_app_secret(datastore_path)
    logger.debug(f"prepare_test_function: Reloaded datastore at {hex(id(datastore))}")
    logger.debug(f"prepare_test_function: Path {datastore.datastore_path}")

    yield

    # Cleanup: Clear watches and queue after test
    try:
        from changedetectionio.flask_app import update_q
        from pathlib import Path

        # Clear the queue to prevent leakage to next test
        while not update_q.empty():
            try:
                update_q.get_nowait()
            except:
                break

        datastore.data['watching'] = {}

        # Delete any old watch metadata JSON files
        base_path = Path(datastore.datastore_path).resolve()
        max_depth = 2

        for file in base_path.rglob("*.json"):
            # Calculate depth relative to base path
            depth = len(file.relative_to(base_path).parts) - 1

            if depth <= max_depth and file.is_file():
                file.unlink()

    except Exception as e:
        logger.warning(f"Error during datastore cleanup: {e}")


# So the app can also know which test name it was
@pytest.fixture(autouse=True)
def set_test_name(request):
  """Automatically set TEST_NAME env var for every test"""
  test_name = request.node.name
  os.environ['PYTEST_CURRENT_TEST'] = test_name
  yield
  # Cleanup if needed


