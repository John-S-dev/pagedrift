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

                    datastore.update_watch(uuid=uuid, update_obj={'last_error': err_text,
                                                                'last_check_status': e.status_code,
                                                                'has_ldjson_price_data': None})
                    process_changedetection_results = False
                    
                except content_fetchers_exceptions.BrowserStepsInUnsupportedFetcher as e:
                    err_text = "This watch has Browser Steps configured and so it cannot run with the 'Basic fast Plaintext/HTTP Client', either remove the Browser Steps or select a Chrome fetcher."
                    datastore.update_watch(uuid=uuid, update_obj={'last_error': err_text})
                    process_changedetection_results = False
                    logger.error(f"Exception (BrowserStepsInUnsupportedFetcher) reached processing watch UUID: {uuid}")

                except Exception as e:
                    import traceback
                    logger.error(f"Worker {worker_id} exception processing watch UUID: {uuid}")
                    logger.exception(f"Worker {worker_id} full exception details:")
                    datastore.update_watch(uuid=uuid, update_obj={'last_error': "Exception: " + str(e)})
                    process_changedetection_results = False

                else:
                    if not datastore.data['watching'].get(uuid):
                        continue

                    update_obj['content-type'] = str(update_handler.fetcher.get_all_headers().get('content-type', '') or "").lower()

                    if not watch.get('ignore_status_codes'):
                        update_obj['consecutive_filter_failures'] = 0

                    update_obj['last_error'] = False
                    cleanup_error_artifacts(uuid, datastore)

                if not datastore.data['watching'].get(uuid):
                    continue

                logger.debug(f"Processing watch UUID: {uuid} - xpath_data length returned {len(update_handler.xpath_data) if update_handler and update_handler.xpath_data else 'empty.'}")
                if update_handler and process_changedetection_results:
                    try:
                        # Reset the edited flag BEFORE update_watch (which calls watch.update() and would set it again)
                        watch.reset_watch_edited_flag()

                        # LLM evaluation — intent filtering + change summary
                        update_obj['_llm_result'] = None
                        update_obj['_llm_intent'] = ''
                        update_obj['_llm_change_summary'] = ''
                        # skip_check: when budget exceeded, don't run LLM or the check.
                        # Also gated on llm_enabled — a disabled LLM can't be spending tokens,
                        # so the budget enforcement shouldn't suppress changes when the user
                        # has explicitly switched LLM off.
                        from changedetectionio.llm.evaluator import is_llm_features_disabled as _is_llm_features_disabled, get_llm_settings as _get_llm_settings
                        _llm_settings = _get_llm_settings(datastore)
                        _llm_master_enabled = _llm_settings.enabled and not _is_llm_features_disabled()
                        _llm_budget_action = _llm_settings.budget_action
                        if _llm_master_enabled and _llm_budget_action == 'skip_check':
                            from changedetectionio.llm.evaluator import is_global_token_budget_exceeded
                            if is_global_token_budget_exceeded(datastore):
                                logger.info(f"LLM monthly budget exceeded — skipping check for {uuid} (budget_action=skip_check)")
                                changed_detected = False

                        # Only run AI intent/summary when there's a PREVIOUS snapshot to diff
                        # against. On the very first check history_n is 0 (the new snapshot is
                        # saved further below), so there's no "change" to describe — running the
                        # LLM here would summarise the whole page as if it just changed (e.g.
                        # "price updated to 860" on first sight). Mirrors the notification gate
                        # (which only fires at history_n >= 2).
                        if changed_detected and watch.history_n >= 1:
                            try:
                                from changedetectionio.llm.evaluator import (
                                    evaluate_change, llm_enabled_for_watch, resolve_intent,
                                    resolve_llm_field, summarise_change, _runtime_llm_config,
                                )
                                # Per-watch (or group-wide) AI on/off — #4204. Checked before
                                # any diff work so a switched-off watch costs nothing.
                                _llm_on, _llm_on_source = llm_enabled_for_watch(watch, datastore)
                                if not _llm_on:
                                    logger.debug(f"LLM disabled for {uuid} (by {_llm_on_source}) — skipping AI intent/summary")
                                # _runtime_llm_config returns None (and logs a debug skip
                                # message) when the master 'llm_enabled' toggle is off, so
                                # the whole block — diff computation, status minitext, and
                                # the two executor dispatches — is skipped, not just the
                                # inner LLM lookups.
                                _llm_cfg = _runtime_llm_config(datastore) if _llm_on else None
                                if _llm_cfg:
                                    # Compute unified diff once — used by both intent and summary
                                    _watch_dates = list(watch.history.keys())
                                    # Capture from_version before new snapshot is added
                                    _llm_from_version = _watch_dates[-1] if _watch_dates else None
                                    if _watch_dates:
                                        _prev_text = watch.get_history_snapshot(timestamp=_watch_dates[-1]) or ''
                                        from difflib import unified_diff as _unified_diff
                                        _diff_lines = list(_unified_diff(
                                            _prev_text.splitlines(keepends=True),
                                            contents.splitlines(keepends=True),
                                            lineterm='',
                                            n=3
                                        ))
                                        _diff_text = ''.join(_diff_lines) if _diff_lines else contents
                                    else:
                                        _diff_text = contents

                                    # Step 1: AI Change Intent — may suppress notification
                                    _llm_intent, _llm_intent_source = resolve_intent(watch, datastore)
                                    if _llm_intent:
                                        set_watch_minitext_status(watch, "AI/LLM (rules)..")
                                        _llm_result = await loop.run_in_executor(
                                            executor,
                                            lambda diff=_diff_text, snap=contents: evaluate_change(
                                                watch, datastore, diff=diff, current_snapshot=snap
                                            )
                                        )
                                        update_obj['_llm_result'] = _llm_result
                                        update_obj['_llm_intent'] = _llm_intent

                                        if _llm_result and not _llm_result.get('important', True):
                                            changed_detected = False
                                            logger.info(
                                                f"LLM filtered out change for {uuid} "
                                                f"(intent from {_llm_intent_source}): "
                                                f"{_llm_result.get('summary', '')[:80]}"
                                            )

                                    # Step 2: AI Change Summary — only compute it when a notification
                                    # is actually going to be sent, because that's the only place
                                    # the worker needs it (it fills {{diff}}/{{llm_summary}} in the
                                    # notification body). The watch-list / diff-page "Summary" button
                                    # computes it on demand via the diff_llm_summary AJAX endpoint, so
                                    # we deliberately do NOT pre-compute it here just for the UI —
                                    # that would spend tokens on every change for a summary nobody
                                    # may ever look at.
                                    from changedetectionio.notification_service import watch_will_send_content_changed_notification
                                    if changed_detected and watch_will_send_content_changed_notification(datastore, watch):
                                        set_watch_minitext_status(watch, "AI/LLM (summary)..")
                                        _change_summary = await loop.run_in_executor(
                                            executor,
                                            lambda diff=_diff_text, snap=contents: summarise_change(
                                                watch, datastore, diff=diff, current_snapshot=snap
                                            )
                                        )
                                        if _change_summary:
                                            update_obj['_llm_change_summary'] = _change_summary
                            except Exception as e:
                                logger.warning(f"LLM evaluation error for {uuid}: {e}")

                        datastore.update_watch(uuid=uuid, update_obj=update_obj)

                        if changed_detected or not watch.history_n:
                            if update_handler.screenshot:
                                watch.save_screenshot(screenshot=update_handler.screenshot)
                                # Free screenshot memory immediately after saving
                                update_handler.screenshot = None
                                if hasattr(update_handler, 'fetcher') and hasattr(update_handler.fetcher, 'screenshot'):
                                    update_handler.fetcher.screenshot = None

                            if update_handler.xpath_data:
                                watch.save_xpath_data(data=update_handler.xpath_data)
                                # Free xpath data memory
                                update_handler.xpath_data = None
                                if hasattr(update_handler, 'fetcher') and hasattr(update_handler.fetcher, 'xpath_data'):
                                    update_handler.fetcher.xpath_data = None

                            # Ensure unique timestamp for history
                            if watch.newest_history_key and int(fetch_start_time) == int(watch.newest_history_key):
                                logger.warning(f"Timestamp {fetch_start_time} already exists, waiting 1 seconds")
                                fetch_start_time += 1
                                await asyncio.sleep(1)

                            watch.save_history_blob(contents=contents,
                                                    timestamp=int(fetch_start_time),
                                                    snapshot_id=update_obj.get('previous_md5', 'none'))

def cleanup_error_artifacts(uuid, datastore):
    """Helper function to clean up error artifacts"""
    cleanup_files = ["last-error-screenshot.png", "last-error.txt"]
    for f in cleanup_files:
        full_path = os.path.join(datastore.datastore_path, uuid, f)
        if os.path.isfile(full_path):
            os.unlink(full_path)

async def send_content_changed_notification(watch_uuid, notification_q, datastore):
    """Helper function to queue notifications using the new notification service"""
    try:
        from changedetectionio.notification_service import create_notification_service
        
        # Create notification service instance
        notification_service = create_notification_service(datastore, notification_q)
        
        notification_service.send_content_changed_notification(watch_uuid)
    except Exception as e:
        logger.error(f"Error sending notification for {watch_uuid}: {e}")


