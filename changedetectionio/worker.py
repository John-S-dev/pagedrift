from blinker import signal
from .processors.exceptions import ProcessorException
import changedetectionio.content_fetchers.exceptions as content_fetchers_exceptions
from changedetectionio.processors.text_json_diff.processor import FilterNotFoundInResponse
from changedetectionio import html_tools
from changedetectionio import worker_pool
from changedetectionio.queuedWatchMetaData import PrioritizedItem
from changedetectionio.pluggy_interface import apply_update_handler_alter, apply_update_finalize

import asyncio
import os
import re
import sys
import time

# Allow alphanumerics, space, and a small set of punctuation that appears in legitimate
# status strings ("Querying AI/LLM (intent)..", "Fetching..."). Anything that could
# be HTML-active (<, >, &, ", ', =, ;, {, }, `, \) is stripped.
_MINITEXT_STATUS_SAFE_RE = re.compile(r'[^A-Za-z0-9 ().,/:\-]')
_MINITEXT_STATUS_MAX_LEN = 80

from loguru import logger

# Async version of update_worker
# Processes jobs from AsyncSignalPriorityQueue instead of threaded queue

IN_PYTEST = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
DEFER_SLEEP_TIME_ALREADY_QUEUED = 0.3 if IN_PYTEST else 10.0


def set_watch_minitext_status(watch, status):
    """
    Set a transient status line for a watch (e.g. "Fetching...", "Querying AI/LLM..").

    Writes to watch['__check_status'] so a client reloading the page can render the
    last known status, and fires the realtime signal so already-connected clients
    update live. __-prefixed key is filtered from disk by Watch._get_commit_data().

    Status is sanitized to alphanumerics, space, and safe punctuation only.
    """
    safe_status = _MINITEXT_STATUS_SAFE_RE.sub('', str(status))[:_MINITEXT_STATUS_MAX_LEN]
    watch['__check_status'] = safe_status
    signal('watch_small_status_comment').send(watch_uuid=watch['uuid'], status=safe_status)


async def async_update_worker(worker_id, q, notification_q, app, datastore, executor=None):
    """
    Async worker function that processes watch check jobs from the queue.

    Args:
        worker_id: Unique identifier for this worker
        q: AsyncSignalPriorityQueue containing jobs to process
        notification_q: Standard queue for notifications
        app: Flask application instance
        datastore: Application datastore
        executor: ThreadPoolExecutor for queue operations (optional)

    Returns:
        "restart" if worker should restart, "shutdown" for clean exit
    """
    # Set a descriptive name for this task
    task = asyncio.current_task()
    if task:
        task.set_name(f"async-worker-{worker_id}")

    # Read restart policy from environment
    max_jobs = int(os.getenv("WORKER_MAX_JOBS", "10"))
    max_runtime_seconds = int(os.getenv("WORKER_MAX_RUNTIME", "3600"))  # 1 hour default

    jobs_processed = 0
    start_time = time.time()

    # Log thread name for debugging
    import threading
    thread_name = threading.current_thread().name
    logger.info(f"Starting async worker {worker_id} on thread '{thread_name}' (max_jobs={max_jobs}, max_runtime={max_runtime_seconds}s)")

def cleanup_error_artifacts(uuid, datastore):
    """Helper function to clean up error artifacts"""
    cleanup_files = ["last-error-screenshot.png", "last-error.txt"]
    for f in cleanup_files:
        full_path = os.path.join(datastore.datastore_path, uuid, f)
        if os.path.isfile(full_path):
            os.unlink(full_path)

