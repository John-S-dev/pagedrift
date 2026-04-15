
# HORRIBLE HACK BUT WORKS :-) PR anyone?
#
# Why?
# `browsersteps_playwright_browser_interface.chromium.connect_over_cdp()` will only run once without async()
# - this flask app is not async()
# - A single timeout/keepalive which applies to the session made at .connect_over_cdp()
#
# So it means that we must unfortunately for now just keep a single timer since .connect_over_cdp() was run
# and know when that reaches timeout/keepalive :( when that time is up, restart the connection and tell the user
# that their time is up, insert another coin. (reload)
#
#

from changedetectionio.strtobool import strtobool
from flask import Blueprint, request, make_response
import os

from changedetectionio.store import ChangeDetectionStore
from changedetectionio.blueprint import plaintext_response
from changedetectionio.flask_app import login_optionally_required
from changedetectionio.validate_url import validate_fetch_url_async
from loguru import logger

browsersteps_sessions = {}
browsersteps_watch_to_session = {}  # Maps watch_uuid -> browsersteps_session_id
io_interface_context = None
import json
import hashlib
from flask import Response
import asyncio
import threading
import time

# Dedicated event loop for ALL browser steps sessions
_browser_steps_loop = None
_browser_steps_thread = None
_browser_steps_loop_lock = threading.Lock()

async def acquire_browser_for_fetcher(fetcher_name, proxy=None, keepalive_ms=None):
    """Acquire a Playwright browser for the given fetcher backend.

    Mirrors normal fetching: fetchers that launch their own browser (e.g. CloakBrowser)
    provide get_browsersteps_browser(); otherwise we connect over CDP to the configured
    Playwright/sockpuppetbrowser driver. Returns (browser, playwright_context).
    """
    from changedetectionio import content_fetchers
    from playwright.async_api import async_playwright

    logger.debug(f"acquire_browser_for_fetcher: requested fetcher='{fetcher_name}', proxy={'yes' if proxy else 'no'}, keepalive_ms={keepalive_ms}")

    browser = None
    playwright_context = None

    # If the fetcher has its own browser launch (runs locally rather than via CDP), use it.
    fetcher_class = getattr(content_fetchers, fetcher_name, None) if fetcher_name else None
    if fetcher_class and hasattr(fetcher_class, 'get_browsersteps_browser'):
        logger.debug(f"acquire_browser_for_fetcher: fetcher '{fetcher_name}' provides its own browser, launching locally")
        result = await fetcher_class.get_browsersteps_browser(proxy=proxy, keepalive_ms=keepalive_ms)
        if result is not None:
            browser, playwright_context = result
            logger.info(f"acquire_browser_for_fetcher: using fetcher-specific browser for '{fetcher_name}'")
        else:
            logger.debug(f"acquire_browser_for_fetcher: '{fetcher_name}' returned no browser, falling back to CDP")
    else:
        logger.debug(f"acquire_browser_for_fetcher: fetcher '{fetcher_name}' has no get_browsersteps_browser(), using CDP")

    # Default: connect to the remote Playwright/sockpuppetbrowser via CDP
    if browser is None:
        base_url = os.getenv('PLAYWRIGHT_DRIVER_URL', '').strip('"')
        logger.debug(f"acquire_browser_for_fetcher: connecting over CDP to '{base_url}' for fetcher '{fetcher_name}'")
        playwright_context = await async_playwright().start()
        a = "?" if '?' not in base_url else '&'
        connect_url = base_url + a + f"timeout={keepalive_ms}"
        browser = await playwright_context.chromium.connect_over_cdp(connect_url, timeout=keepalive_ms)
        logger.info(f"acquire_browser_for_fetcher: connected over CDP for fetcher '{fetcher_name}'")

    return browser, playwright_context


def cleanup_expired_sessions():
    """Remove expired browsersteps sessions and cleanup their resources"""
    global browsersteps_sessions, browsersteps_watch_to_session

    expired_session_ids = []

    # Find expired sessions
    for session_id, session_data in browsersteps_sessions.items():
        browserstepper = session_data.get('browserstepper')
        if browserstepper and browserstepper.has_expired:
            expired_session_ids.append(session_id)

    # Cleanup expired sessions
    for session_id in expired_session_ids:
        logger.debug(f"Cleaning up expired browsersteps session {session_id}")
        session_data = browsersteps_sessions[session_id]

        try:
            run_async_in_browser_loop(_close_session_resources(session_data, label=f" for session {session_id}"))
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")

        # Remove from sessions dict
        del browsersteps_sessions[session_id]

        # Remove from watch mapping
        for watch_uuid, mapped_session_id in list(browsersteps_watch_to_session.items()):
            if mapped_session_id == session_id:
                del browsersteps_watch_to_session[watch_uuid]
                break

    if expired_session_ids:
        logger.info(f"Cleaned up {len(expired_session_ids)} expired browsersteps session(s)")

