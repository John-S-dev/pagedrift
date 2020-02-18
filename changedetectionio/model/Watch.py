"""
Watch domain model for change detection monitoring.

ARCHITECTURE NOTE: Configuration Override Hierarchy
===================================================

This module implements Watch objects that inherit from dict (technical debt).
The dream architecture would use Pydantic for:

1. CHAIN RESOLUTION (Watch → Tag → Global Settings)
   - Current: Manual resolution scattered across codebase
   - Future: @computed_field properties with automatic resolution
   - Examples: resolved_fetch_backend, resolved_restock_settings, etc.

2. DATABASE BACKEND ABSTRACTION
   - Current: Domain model tightly coupled to file-based JSON storage
   - Future: Domain model (Pydantic) separate from persistence layer
   - Enables: Easy migration to PostgreSQL, MongoDB, etc.

3. TYPE SAFETY & VALIDATION
   - Current: Dict access with no compile-time checks
   - Future: Type hints, IDE autocomplete, validation at boundaries

See class model docstring for detailed explanation and examples.
See: processors/restock_diff/processor.py:184-192 for manual resolution example
"""

from blinker import signal
from changedetectionio.validate_url import is_safe_valid_url

from changedetectionio.strtobool import strtobool
from changedetectionio.jinja2_custom import render as jinja_render
from . import watch_base
from .persistence import EntityPersistenceMixin
import os
import re
from pathlib import Path
from loguru import logger

# Module-level favicon filename cache: data_dir → basename (or None)
# Keyed by data_dir so it survives Watch object recreation, deepcopy, and concurrent requests.
# Invalidated explicitly when the favicon is saved or the watch history is cleared.
_FAVICON_FILENAME_CACHE: dict = {}

minimum_seconds_recheck_time = int(os.getenv('MINIMUM_SECONDS_RECHECK_TIME', 3))
mtable = {'seconds': 1, 'minutes': 60, 'hours': 3600, 'days': 86400, 'weeks': 86400 * 7}

def _brotli_save(contents, filepath, mode=None, fallback_uncompressed=False):
    """
    Save compressed data using native brotli with streaming compression.
    Uses chunked compression to minimize peak memory usage and malloc_trim()
    to force release of C-level memory back to the OS.

    Args:
        contents: data to compress (str or bytes)
        filepath: destination file path
        mode: brotli compression mode (e.g., brotli.MODE_TEXT)
        fallback_uncompressed: if True, save uncompressed on failure; if False, raise exception

    Returns:
        str: actual filepath saved (may differ from input if fallback used)

    Raises:
        Exception: if compression fails and fallback_uncompressed is False
    """
    import brotli
    import gc
    import ctypes

    # Ensure contents are bytes
    if isinstance(contents, str):
        contents = contents.encode('utf-8')

    try:
        original_size = len(contents)
        logger.debug(f"Starting brotli streaming compression of {original_size} bytes.")

        # Create streaming compressor
        compressor = brotli.Compressor(quality=6, mode=mode if mode is not None else brotli.MODE_GENERIC)

        # Stream compress in chunks to minimize memory usage
        chunk_size = 65536  # 64KB chunks
        total_compressed_size = 0

        with open(filepath, 'wb') as f:
            # Process data in chunks
            offset = 0
            while offset < len(contents):
                chunk = contents[offset:offset + chunk_size]
                compressed_chunk = compressor.process(chunk)
                if compressed_chunk:
                    f.write(compressed_chunk)
                    total_compressed_size += len(compressed_chunk)
                offset += chunk_size

