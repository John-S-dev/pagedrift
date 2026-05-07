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

from .. import jinja2_custom as safe_jinja
from ..html_tools import TRANSLATE_WHITESPACE_TABLE

FAVICON_RESAVE_THRESHOLD_SECONDS=86400
BROTLI_COMPRESS_SIZE_THRESHOLD = int(os.getenv('SNAPSHOT_BROTLI_COMPRESSION_THRESHOLD', 1024*20))

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

            # Finalize compression - critical for proper cleanup
            final_chunk = compressor.finish()
            if final_chunk:
                f.write(final_chunk)
                total_compressed_size += len(final_chunk)

        logger.debug(f"Finished brotli compression - From {original_size} to {total_compressed_size} bytes.")

        # Cleanup: Delete compressor, force Python GC, then force C-level memory release
        del compressor
        gc.collect()

        # Force release of C-level memory back to OS (since brotli is a C library)
        try:
            ctypes.CDLL('libc.so.6').malloc_trim(0)
        except Exception:
            pass  # malloc_trim not available on all systems (e.g., macOS)

        return filepath

    except Exception as e:
        logger.error(f"Brotli compression error: {e}")

        # Compression failed
        if fallback_uncompressed:
            logger.warning(f"Brotli compression failed for {filepath}, saving uncompressed")
            fallback_path = filepath.replace('.br', '')
            with open(fallback_path, 'wb') as f:
                f.write(contents)
            return fallback_path
        else:
            raise Exception(f"Brotli compression failed for {filepath}: {e}")


class model(EntityPersistenceMixin, watch_base):
    """
    Watch domain model for monitoring URL changes.

    Inherits from watch_base (which inherits dict) - see watch_base docstring for field documentation.

    ## Configuration Override Hierarchy (Chain Resolution)

    The dream architecture uses a 3-level resolution chain:
        Watch settings → Tag/Group settings → Global settings

    Current implementation is MANUAL (see processor.py:184-192 for example):
        - Processors manually check watch.get('field')
        - Then loop through watch.tags to find first tag with overrides_watch=True
        - Finally fall back to datastore['settings']['application']['field']

    FUTURE: Pydantic-based chain resolution would enable:

        ```python
        # Instead of manual resolution in every processor:
        restock_settings = watch.get('restock_settings', {})
        for tag_uuid in watch.get('tags'):
            tag = datastore['settings']['application']['tags'][tag_uuid]
            if tag.get('overrides_watch'):
                restock_settings = tag.get('restock_settings', {})
                break

        # Clean computed properties with automatic resolution:
        @computed_field
        def resolved_restock_settings(self) -> dict:
            if self.restock_settings:
                return self.restock_settings
            for tag_uuid in self.tags:
                tag = self._datastore.get_tag(tag_uuid)
                if tag.overrides_watch and tag.restock_settings:
                    return tag.restock_settings
            return self._datastore.settings.restock_settings or {}

        # Usage: watch.resolved_restock_settings (automatic, type-safe, tested once)
        ```

    def clear_watch(self):
        import pathlib

        # Get list of processor config files to preserve
        from changedetectionio.processors import find_processors
        processor_names = [name for cls, name in find_processors()]
        processor_config_files = {f"{name}.json" for name in processor_names}

        # JSON Data, Screenshots, Textfiles (history index and snapshots), HTML in the future etc
        # But preserve processor config files (they're configuration, not history data)
        # Use glob not rglob here for safety.
        for item in pathlib.Path(str(self.data_dir)).glob("*.*"):
            # Skip processor config files
            if item.name in processor_config_files:
                continue
            os.unlink(item)

        _FAVICON_FILENAME_CACHE.pop(self.data_dir, None)

        # Force the attr to recalculate
        bump = self.history

        # Do this last because it will trigger a recheck due to last_checked being zero
        self.update({
            'browser_steps_last_error_step': None,
            'check_count': 0,
            'fetch_time': 0.0,
            'has_ldjson_price_data': None,
            'last_checked': 0,
            'last_error': False,
            'last_notification_error': False,
            'last_viewed': 0,
            'previous_md5': False,
            'remote_server_reply': None,
            'track_ldjson_price_data': None
        })
        watch_check_update = signal('watch_check_update')
        if watch_check_update:
            watch_check_update.send(watch_uuid=self.get('uuid'))

        return

    @property
    def is_source_type_url(self):
        return self.get('url', '').startswith('source:')

    @property
    def get_fetch_backend(self):
        """
        Get the fetch backend for this watch with special case handling.

        CHAIN RESOLUTION OPPORTUNITY:
        Currently returns watch.fetch_backend directly, but doesn't implement
        Watch → Tag → Global resolution chain. With Pydantic:

        @computed_field
        def resolved_fetch_backend(self) -> str:
            # Special case: PDFs always use html_requests
            if self.is_pdf:
                return 'html_requests'

            # Watch override
            if self.fetch_backend and self.fetch_backend != 'system':
                return self.fetch_backend

            # Tag override (first tag with overrides_watch=True wins)
            for tag_uuid in self.tags:
                tag = self._datastore.get_tag(tag_uuid)
                if tag.overrides_watch and tag.fetch_backend:
                    return tag.fetch_backend

            # Global default
            return self._datastore.settings.fetch_backend
        """
        # Maybe also if is_image etc?
        # This is because chrome/playwright wont render the PDF in the browser and we will just fetch it and use pdf2html to see the text.
        if self.is_pdf:
            return 'html_requests'

        return self.get('fetch_backend')

    @property
    def fetcher_supports_screenshots(self):
        """Return True if the fetcher configured for this watch supports screenshots.

        """Unfortunately for now timestamp is stored as string key"""
        keys = list(self.history.keys())
        if not keys:
            return None
        if len(keys) == 1:
            return keys[0]

        last_viewed = int(self.get('last_viewed'))
        sorted_keys = sorted(keys, key=lambda x: int(x))
        sorted_keys.reverse()

        # When the 'last viewed' timestamp is greater than or equal the newest snapshot, return second newest
        if last_viewed >= int(sorted_keys[0]):
            return sorted_keys[1]
        
        # When the 'last viewed' timestamp is between snapshots, return the older snapshot
        for newer, older in list(zip(sorted_keys[0:], sorted_keys[1:])):
            if last_viewed < int(newer) and last_viewed >= int(older):
                return older

        # When the 'last viewed' timestamp is less than the oldest snapshot, return oldest
        return sorted_keys[-1]

    def get_history_snapshot(self, timestamp=None, filepath=None):
        """
        Accepts either timestamp or filepath
        :param timestamp:
        :param filepath:
        :return:
        """
        import brotli

        if not filepath:
            filepath = self.history[timestamp]

        # Confine every read to the watch's own data directory — defence in depth
        # against any path that bypasses the history parser (e.g. direct filepath= callers).
        # Set HISTORY_SNAPSHOT_FILE_ALLOW_OUTSIDE_WATCH_DATADIR=true to disable (not recommended).
        if self.data_dir and not strtobool(os.getenv('HISTORY_SNAPSHOT_FILE_ALLOW_OUTSIDE_WATCH_DATADIR', 'False')):
            safe_data_dir = os.path.realpath(self.data_dir)
            resolved = os.path.realpath(filepath)
            if not (resolved.startswith(safe_data_dir + os.sep) or resolved == safe_data_dir):
                raise PermissionError(f"Snapshot path {filepath!r} is outside the watch data directory")

        # Check if binary file (image, PDF, etc.)
        # Binary files are NEVER saved with .br compression, only text files are
        binary_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.bin', '.jfif')
        is_binary = any(filepath.endswith(ext) for ext in binary_extensions)

        # Only look for .br versions for text files
        if not is_binary:
            # See if a brotli version exists and switch to that (text files only)
            if not filepath.endswith('.br') and os.path.isfile(f"{filepath}.br"):
                filepath = f"{filepath}.br"

            # OR in the backup case that the .br does not exist, but the plain one does
            if filepath.endswith('.br') and not os.path.isfile(filepath):
                if os.path.isfile(filepath.replace('.br', '')):
                    filepath = filepath.replace('.br', '')

        # Handle .br compressed text files
        if filepath.endswith('.br'):
            # Brotli doesnt have a fileheader to detect it, so we rely on filename
            # https://www.rfc-editor.org/rfc/rfc7932
            # Note: .br should ONLY exist for text files, never binary
            with open(filepath, 'rb') as f:
                return brotli.decompress(f.read()).decode('utf-8')

        # Binary file - return raw bytes
        if is_binary:
            with open(filepath, 'rb') as f:
                return f.read()

        # Text file - decode to string
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _write_atomic(self, dest, data, mode='wb'):
        """Write data atomically to dest using a temp file"""
        import tempfile
        with tempfile.NamedTemporaryFile(mode, delete=False, dir=self.data_dir) as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, dest)

    def history_trim(self, newest_n_items):
        from pathlib import Path
        import gc
        # Sort by timestamp (key)
        sorted_items = sorted(self.history.items(), key=lambda x: int(x[0]))

