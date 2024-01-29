#!/usr/bin/env python3

# Read more https://github.com/dgtlmoon/changedetection.io/wiki
# Semver means never use .01, or 00. Should be .1.
__version__ = '0.60.4'

from changedetectionio.strtobool import strtobool
from json.decoder import JSONDecodeError

from loguru import logger
import getopt
import logging
import os
import platform
import signal
import threading
import time

# Eventlet completely removed - using threading mode for SocketIO
# This provides better Python 3.12+ compatibility and eliminates eventlet/asyncio conflicts
# Note: store and changedetection_app are imported inside main() to avoid
# initialization before argument parsing (allows --help to work without loading everything)

# ==============================================================================
# Multiprocessing Configuration - CRITICAL for Thread Safety
# ==============================================================================
#
# PROBLEM: Python 3.12+ warns about fork() with multi-threaded processes:
#   "This process is multi-threaded, use of fork() may lead to deadlocks"
#
# WHY IT'S DANGEROUS:
#   1. This Flask app has multiple threads (HTTP handlers, workers, SocketIO)
#   2. fork() copies ONLY the calling thread to the child process
#   3. BUT fork() also copies all locks/mutexes in their current state
#   4. If another thread held a lock during fork() → child has locked lock with no owner
#   5. Result: PERMANENT DEADLOCK if child tries to acquire that lock
#
# SOLUTION: Use 'spawn' instead of 'fork'
#   - spawn starts a fresh Python interpreter (no inherited threads or locks)
#   - Slower (~200ms vs ~1ms) but safe with multi-threaded parent
#   - Consistent across all platforms (Windows already uses spawn by default)
#
# IMPLEMENTATION:
#   1. Explicit contexts everywhere (primary protection):
#      - playwright.py: ctx = multiprocessing.get_context('spawn')
#      - puppeteer.py: ctx = multiprocessing.get_context('spawn')
#      - isolated_opencv.py: ctx = multiprocessing.get_context('spawn')
#      - isolated_libvips.py: ctx = multiprocessing.get_context('spawn')
#
#   2. Global default (defense-in-depth, below):
#      - Safety net if future code forgets explicit context
#      - Protects against third-party libraries using Process()
#      - Costs nothing (explicit contexts always override it)
#
# WHY BOTH?
#   - Explicit contexts: Clear, self-documenting, always works
#   - Global default: Safety net for forgotten contexts or library code
#   - If someone writes "Process()" instead of "ctx.Process()", still safe!
#
# See: https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods
# ==============================================================================

import multiprocessing
import os
import sys

# Limit glibc malloc arena count to prevent RSS growth from concurrent requests.
# Default: glibc creates up to 8×CPU_cores arenas. Each concurrent thread/connection
# can trigger a new arena, and freed memory stays mapped in those arenas as RSS forever.
# With MALLOC_ARENA_MAX=2, at most 2 arenas are used; freed pages return to the OS faster.
# Must be set before worker threads start; env var is read lazily by glibc on first arena creation.
if 'MALLOC_ARENA_MAX' not in os.environ:
    os.environ['MALLOC_ARENA_MAX'] = '2'
    try:
        import ctypes as _ctypes
        _ctypes.CDLL('libc.so.6').mallopt(-8, 2)  # M_ARENA_MAX = -8
    except Exception:
        pass

# Set spawn as global default (safety net - all our code uses explicit contexts anyway)
# Skip in tests to avoid breaking pytest-flask's LiveServer fixture (uses unpicklable local functions)
if 'pytest' not in sys.modules:
    try:
        if multiprocessing.get_start_method(allow_none=True) is None:
            multiprocessing.set_start_method('spawn', force=False)
            logger.debug("Set multiprocessing default to 'spawn' for thread safety (explicit contexts used everywhere)")
    except RuntimeError:
        logger.debug(f"Multiprocessing start method already set: {multiprocessing.get_start_method()}")

# Only global so we can access it in the signal handler
app = None
datastore = None

def get_version():
    return __version__

# Parent wrapper or OS sends us a SIGTERM/SIGINT, do everything required for a clean shutdown
def sigshutdown_handler(_signo, _stack_frame):
    name = signal.Signals(_signo).name
    logger.critical(f'Shutdown: Got Signal - {name} ({_signo}), Fast shutdown initiated')

    # Set exit flag immediately to stop all loops
    app.config.exit.set()
    datastore.stop_thread = True

    # Log memory consumption before shutting down workers (cross-platform)
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        rss_mb = mem_info.rss / 1024 / 1024
        vms_mb = mem_info.vms / 1024 / 1024
        logger.info(f"Memory consumption before worker shutdown: RSS={rss_mb:,.2f} MB, VMS={vms_mb:,.2f} MB")
    except Exception as e:
        logger.warning(f"Could not retrieve memory stats: {str(e)}")

    # Shutdown workers and queues immediately
    try:
        from changedetectionio import worker_pool
        worker_pool.shutdown_workers()
    except Exception as e:
        logger.error(f"Error shutting down workers: {str(e)}")
    
    # Close janus queues properly
    try:
        from changedetectionio.flask_app import update_q, notification_q
        update_q.close()
        notification_q.close()
        logger.debug("Queues closed successfully")
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to close queues: {e}")
    
    # Shutdown socketio server fast
    from changedetectionio.flask_app import socketio_server
    if socketio_server and hasattr(socketio_server, 'shutdown'):
        try:
            socketio_server.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down Socket.IO server: {str(e)}")
    
    # With immediate persistence, all data is already saved
    logger.success('All data already persisted (immediate commits enabled).')

    sys.exit()

def print_help():
    """Print help text for command line options"""
    print('Usage: changedetection.py [options]')
    print('')
    print('Standard options:')
    print('  -s                SSL enable')
    print('  -h HOST           Listen host (default: 0.0.0.0)')
    print('  -p PORT           Listen port (default: 5000)')
    print('  -d PATH           Datastore path')
    print('  -l LEVEL          Log level (TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)')
    print('  -c                Cleanup unused snapshots')
    print('  -C                Create datastore directory if it doesn\'t exist')
    print('  -P true/false     Set all watches paused (true) or active (false)')
    print('')
    print('Add URLs on startup:')
    print('  -u URL            Add URL to watch (can be used multiple times)')
    print('  -u0 \'JSON\'        Set options for first -u URL (e.g. \'{"processor":"text_json_diff"}\')')
    print('  -u1 \'JSON\'        Set options for second -u URL (0-indexed)')
    print('  -u2 \'JSON\'        Set options for third -u URL, etc.')
    print('                    Available options: processor, fetch_backend, headers, method, etc.')
    print('                    See model/Watch.py for all available options')
    print('')
    print('Recheck on startup:')
    print('  -r all            Queue all watches for recheck on startup')
    print('  -r UUID,...       Queue specific watches (comma-separated UUIDs)')
    print('  -r all N          Queue all watches, wait for completion, repeat N times')
    print('  -r UUID,... N     Queue specific watches, wait for completion, repeat N times')
    print('')
    print('Batch mode:')
    print('  -b                Run in batch mode (process queue then exit)')
    print('                    Useful for CI/CD, cron jobs, or one-time checks')
    print('                    NOTE: Batch mode checks if Flask is running and aborts if port is in use')
    print('                    Use -p PORT to specify a different port if needed')
    print('')

def main():
    global datastore
    global app

    # Early help/version check before any initialization
    if '--help' in sys.argv or '-help' in sys.argv:
        print_help()
        sys.exit(0)

    if '--version' in sys.argv or '-v' in sys.argv:
        print(f'changedetection.io {__version__}')
        sys.exit(0)

    # Import heavy modules after help/version checks to keep startup fast for those flags
    from changedetectionio import store
    from changedetectionio.flask_app import changedetection_app

    datastore_path = None
    # Set a default logger level
    logger_level = 'DEBUG'
    include_default_watches = True
    all_paused = None  # None means don't change, True/False to set

    host = os.environ.get("LISTEN_HOST", "0.0.0.0").strip()
    port = int(os.environ.get('PORT', 5000))
    ssl_mode = False

    # Lists for multiple URLs and their options
    urls_to_add = []
    url_options = {}  # Key: index (0-based), Value: dict of options
    recheck_watches = None  # None, 'all', or list of UUIDs
    recheck_repeat_count = 1  # Number of times to repeat recheck cycle
    batch_mode = False  # Run once then exit when queue is empty

    # On Windows, create and use a default path.
    if os.name == 'nt':
        datastore_path = os.path.expandvars(r'%APPDATA%\changedetection.io')
        os.makedirs(datastore_path, exist_ok=True)
    else:
        # Must be absolute so that send_from_directory doesnt try to make it relative to backend/
        datastore_path = os.path.join(os.getcwd(), "../datastore")

        # Start monitor in background thread
        monitor_thread = threading.Thread(target=batch_mode_monitor, daemon=True, name="BatchModeMonitor")
        monitor_thread.start()
        logger.info("Batch mode enabled: Will exit after all queued items are processed")

    # Get the SocketIO instance from the Flask app (created in flask_app.py)
    from changedetectionio.flask_app import socketio_server
    global socketio
    socketio = socketio_server

    signal.signal(signal.SIGTERM, sigshutdown_handler)
    signal.signal(signal.SIGINT, sigshutdown_handler)
    
    # Custom signal handler for memory cleanup
    def sigusr_clean_handler(_signo, _stack_frame):
        from changedetectionio.gc_cleanup import memory_cleanup
        logger.info('SIGUSR1 received: Running memory cleanup')
        return memory_cleanup(app)

    # Register the SIGUSR1 signal handler
    # Only register the signal handler if running on Linux
    if platform.system() == "Linux":
        signal.signal(signal.SIGUSR1, sigusr_clean_handler)
    else:
        logger.info("SIGUSR1 handler only registered on Linux, skipped.")

    app.config['datastore_path'] = datastore_path


    @app.context_processor
    def inject_template_globals():
        from changedetectionio.llm.evaluator import get_llm_config as _get_llm_config
        from flask_login import current_user
        has_password = datastore.data['settings']['application']['password'] != False
        # Don't reveal the running version to anonymous visitors when password protection is enabled (#2190)
        show_version = current_user.is_authenticated or not has_password
        return dict(right_sticky="v"+__version__ if show_version else None,
                    new_version_available=app.config['NEW_VERSION_AVAILABLE'],
                    has_password=has_password,
                    socket_io_enabled=datastore.data['settings']['application'].get('ui', {}).get('socket_io_enabled', True),
                    all_paused=datastore.data['settings']['application'].get('all_paused', False),
                    all_muted=datastore.data['settings']['application'].get('all_muted', False),
                    llm_configured=bool(_get_llm_config(datastore)),
                    unread_changes_count=datastore.unread_changes_count,
                    )

    # Monitored websites will not receive a Referer header when a user clicks on an outgoing link.
    @app.after_request
    def hide_referrer(response):
        if strtobool(os.getenv("HIDE_REFERER", 'false')):
            response.headers["Referrer-Policy"] = "same-origin"

        return response

    # Proxy sub-directory support
    # Set environment var USE_X_SETTINGS=1 on this script
    # And then in your proxy_pass settings
    #
    #         proxy_set_header Host "localhost";
    #         proxy_set_header X-Forwarded-Prefix /app;


    if os.getenv('USE_X_SETTINGS'):
        logger.info("USE_X_SETTINGS is ENABLED")
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,      # X-Forwarded-For (client IP)
            x_proto=1,    # X-Forwarded-Proto (http/https)
            x_host=1,     # X-Forwarded-Host (original host)
            x_port=1,     # X-Forwarded-Port (original port)
            x_prefix=1    # X-Forwarded-Prefix (URL prefix)
        )


    # In batch mode, skip starting the HTTP server - just keep workers running
    if batch_mode:
        logger.info("Batch mode: Skipping HTTP server startup, workers will process queue")
        logger.info("Batch mode: Main thread will wait for shutdown signal")
        # Keep main thread alive until batch monitor triggers shutdown
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Batch mode: Keyboard interrupt received")
            pass
    else:
        # Normal mode: Start HTTP server
        # SocketIO instance is already initialized in flask_app.py
        if socketio_server:
            if ssl_mode:
                logger.success(f"SSL mode enabled, attempting to start with '{ssl_cert_file}' and '{ssl_privkey_file}' in {os.getcwd()}")
                socketio.run(app, host=host, port=int(port), debug=False,
                             ssl_context=(ssl_cert_file, ssl_privkey_file), allow_unsafe_werkzeug=True)
            else:
                socketio.run(app, host=host, port=int(port), debug=False, allow_unsafe_werkzeug=True)
        else:
            # Run Flask app without Socket.IO if disabled
            logger.info("Starting Flask app without Socket.IO server")
            if ssl_mode:
                logger.success(f"SSL mode enabled, attempting to start with '{ssl_cert_file}' and '{ssl_privkey_file}' in {os.getcwd()}")
                app.run(host=host, port=int(port), debug=False,
                        ssl_context=(ssl_cert_file, ssl_privkey_file))
            else:
                app.run(host=host, port=int(port), debug=False)
