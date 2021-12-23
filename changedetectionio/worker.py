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


