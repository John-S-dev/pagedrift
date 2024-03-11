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

    while not app.config.exit.is_set():
        update_handler = None
        watch = None
        processing_exception = None  # Reset at start of each iteration to prevent state bleeding

        try:
            # Efficient blocking via run_in_executor (no polling overhead!)
            # Worker blocks in threading.Queue.get() which uses Condition.wait()
            # Executor must be sized to match worker count (see worker_pool.py: 50 threads default)
            # Single timeout (no double-timeout wrapper) = no race condition
            queued_item_data = await q.async_get(executor=executor, timeout=1.0)

            # CRITICAL: Claim UUID immediately after getting from queue to prevent race condition
            # in wait_for_all_checks() which checks qsize() and running_uuids separately
            uuid = queued_item_data.item.get('uuid')
            if not worker_pool.claim_uuid_for_processing(uuid, worker_id):
                # Already being processed - re-queue and continue
                logger.trace(f"Worker {worker_id} detected UUID {uuid} already processing during claim - deferring")
                await asyncio.sleep(DEFER_SLEEP_TIME_ALREADY_QUEUED)
                deferred_priority = max(1000, queued_item_data.priority * 10)
                deferred_item = PrioritizedItem(priority=deferred_priority, item=queued_item_data.item)
                worker_pool.queue_item_async_safe(q, deferred_item, silent=True)
                continue

        except asyncio.TimeoutError:
            # No jobs available - check if we should restart based on time while idle
            runtime = time.time() - start_time
            if runtime >= max_runtime_seconds:
                logger.info(f"Worker {worker_id} idle and reached max runtime ({runtime:.0f}s), restarting")
                return "restart"
            continue
        except RuntimeError as e:
            # Handle executor shutdown gracefully - this is expected during shutdown
            if "cannot schedule new futures after shutdown" in str(e):
                # Executor shut down - exit gracefully without logging in pytest
                if not IN_PYTEST:
                    logger.debug(f"Worker {worker_id} detected executor shutdown, exiting")
                break
            # Other RuntimeError - log and continue
            logger.error(f"Worker {worker_id} runtime error: {e}")
            await asyncio.sleep(0.1)
            continue
        except Exception as e:
            # Handle expected Empty exception from queue timeout
            import queue
            if isinstance(e, queue.Empty):
                # Queue is empty, normal behavior - just continue
                continue

            # Unexpected exception - log as critical
            logger.critical(f"CRITICAL: Worker {worker_id} failed to get queue item: {type(e).__name__}: {e}")

            # Log queue health for debugging
            try:
                queue_size = q.qsize()
                is_empty = q.empty()
                logger.critical(f"CRITICAL: Worker {worker_id} queue health - size: {queue_size}, empty: {is_empty}")
            except Exception as health_e:
                logger.critical(f"CRITICAL: Worker {worker_id} queue health check failed: {health_e}")

            await asyncio.sleep(0.1)
            continue

        # UUID already claimed above immediately after getting from queue
        # to prevent race condition with wait_for_all_checks()

        fetch_start_time = round(time.time())

        try:
            if uuid in list(datastore.data['watching'].keys()) and datastore.data['watching'][uuid].get('url'):
                changed_detected = False
                contents = b''
                process_changedetection_results = True
                update_obj = {}

                # Clear last errors
                datastore.data['watching'][uuid]['browser_steps_last_error_step'] = None
                datastore.data['watching'][uuid]['last_checked'] = fetch_start_time

                watch = datastore.data['watching'].get(uuid)

                logger.info(f"Worker {worker_id} processing watch UUID {uuid} Priority {queued_item_data.priority} URL {watch['url']}")

                try:
                    # Retrieve signal by name to ensure thread-safe access across worker threads
                    watch_check_update = signal('watch_check_update')
                    watch_check_update.send(watch_uuid=uuid)

                    # Processor is what we are using for detecting the "Change"
                    processor = watch.get('processor', 'text_json_diff')

                    # Init a new 'difference_detection_processor'
                    # Use get_processor_module() to support both built-in and plugin processors
                    from changedetectionio.processors import get_processor_module
                    processor_module = get_processor_module(processor)

                    if not processor_module:
                        error_msg = f"Processor module '{processor}' not found."
                        logger.error(error_msg)
                        raise ModuleNotFoundError(error_msg)

                    update_handler = processor_module.perform_site_check(datastore=datastore,
                                                                         watch_uuid=uuid)

                    # Allow plugins to modify/wrap the update_handler
                    update_handler = apply_update_handler_alter(update_handler, watch, datastore)

def cleanup_error_artifacts(uuid, datastore):
    """Helper function to clean up error artifacts"""
    cleanup_files = ["last-error-screenshot.png", "last-error.txt"]
    for f in cleanup_files:
        full_path = os.path.join(datastore.datastore_path, uuid, f)
        if os.path.isfile(full_path):
            os.unlink(full_path)

