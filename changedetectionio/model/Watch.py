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

                        # Always resolve history entries to within the watch's own data directory.
                        # Entries restored from backup could contain absolute or traversal paths —
                        # never trust them. Use realpath to also block symlink-based escapes.
                        safe_data_dir = os.path.realpath(self.data_dir)
                        snapshot_fname = os.path.basename(v.strip())
                        resolved_path = os.path.realpath(os.path.join(self.data_dir, snapshot_fname))

                        if not resolved_path.startswith(safe_data_dir + os.sep) and resolved_path != safe_data_dir:
                            logger.warning(f"Skipping unsafe history entry for {self.get('uuid')}: {v!r}")
                            continue

                        if not os.path.exists(resolved_path):
                            continue

                        tmp_history[k] = resolved_path

        if len(tmp_history):
            self.__newest_history_key = list(tmp_history.keys())[-1]
        else:
            self.__newest_history_key = None

        self.__history_n = len(tmp_history)

        return tmp_history

    @property
    def has_history(self):
        fname = os.path.join(self.data_dir, self.history_index_filename)
        return os.path.isfile(fname)

    @property
    def has_browser_steps(self):
        has_browser_steps = self.get('browser_steps') and list(filter(
            lambda s: (s['operation'] and len(s['operation']) and s['operation'] != 'Choose one' and s['operation'] != 'Goto site'),
            self.get('browser_steps')))

        return has_browser_steps

    @property
    def has_restock_info(self):
        if self.get('restock') and self['restock'].get('in_stock') != None:
                return True

        return False

    # Returns the newest key, but if theres only 1 record, then it's counted as not being new, so return 0.
    @property
    def newest_history_key(self):
        if self.__newest_history_key is not None:
            return self.__newest_history_key

        if len(self.history) <= 1:
            return 0


        bump = self.history
        return self.__newest_history_key

    # Given an arbitrary timestamp, find the best history key for the [diff] button so it can preset a smarter from_version
    @property
    def get_from_version_based_on_last_viewed(self):

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

        keep_part = dict(sorted_items[-newest_n_items:])
        delete_part = dict(sorted_items[:-newest_n_items])
        logger.info( f"[{self.get('uuid')}] Trimming history to most recent {newest_n_items} items, keeping {len(keep_part)} items deleting {len(delete_part)} items.")

        if delete_part:
            for item in delete_part.items():
                try:
                    Path(item[1]).unlink(missing_ok=True)
                except Exception as e:
                    logger.critical(f"{str(e)}")
                finally:
                    logger.debug(f"[{self.get('uuid')}] Deleted {item[1]} history snapshot")
        try:
            dest = os.path.join(self.data_dir, self.history_index_filename)
            output = "\r\n".join(
                f"{k},{Path(v).name}"
                for k, v in keep_part.items()
            )+"\r\n"
            self._write_atomic(dest=dest, data=output, mode='w')
        except Exception as e:
            logger.critical(f"{str(e)}")
        finally:
            logger.debug(f"[{self.get('uuid')}] Updated history index {dest}")

        # reimport
        bump = self.history
        gc.collect()

    # Save some text file to the appropriate path and bump the history
    # result_obj from fetch_site_status.run()
    def save_history_blob(self, contents, timestamp, snapshot_id):

        logger.trace(f"{self.get('uuid')} - Updating {self.history_index_filename} with timestamp {timestamp}")

        self.ensure_data_dir_exists()
        skip_brotli = strtobool(os.getenv('DISABLE_BROTLI_TEXT_SNAPSHOT', 'False'))

        # Binary data - detect file type and save without compression
        if isinstance(contents, bytes):
            try:
                import puremagic
                detections = puremagic.magic_string(contents[:2048])
                ext = detections[0].extension if detections else 'bin'
                # Strip leading dot if present (puremagic returns extensions like '.jfif')
                ext = ext.lstrip('.')
                if detections:
                    logger.trace(f"Detected file type: {detections[0].mime_type} -> extension: {ext}")
            except Exception as e:
                logger.warning(f"puremagic detection failed: {e}, using 'bin' extension")
                ext = 'bin'

            snapshot_fname = f"{snapshot_id}.{ext}"
            dest = os.path.join(self.data_dir, snapshot_fname)
            self._write_atomic(dest, contents)
            logger.trace(f"Saved binary snapshot as {snapshot_fname} ({len(contents)} bytes)")

        # Text data - use brotli compression if enabled and above threshold
        else:
            if not skip_brotli and len(contents) > BROTLI_COMPRESS_SIZE_THRESHOLD:
                # Compressed text
                import brotli
                snapshot_fname = f"{snapshot_id}.txt.br"
                dest = os.path.join(self.data_dir, snapshot_fname)

                if not os.path.exists(dest):
                    try:
                        actual_dest = _brotli_save(contents, dest, mode=brotli.MODE_TEXT, fallback_uncompressed=True)
                        if actual_dest != dest:
                            snapshot_fname = os.path.basename(actual_dest)
                    except Exception as e:
                        logger.error(f"{self.get('uuid')} - Brotli compression failed: {e}")
                        # Fallback to uncompressed
                        snapshot_fname = f"{snapshot_id}.txt"
                        dest = os.path.join(self.data_dir, snapshot_fname)
                        self._write_atomic(dest, contents.encode('utf-8'))
            else:
                # Plain text
                snapshot_fname = f"{snapshot_id}.txt"
                dest = os.path.join(self.data_dir, snapshot_fname)
                self._write_atomic(dest, contents.encode('utf-8'))

        # Append to history.txt atomically
        index_fname = os.path.join(self.data_dir, self.history_index_filename)
        index_line = f"{timestamp},{snapshot_fname}\n"

        with open(index_fname, 'a', encoding='utf-8') as f:
            f.write(index_line)
            f.flush()
            os.fsync(f.fileno())

        # Update internal state
        self.__newest_history_key = timestamp
        self.__history_n += 1

        # MANUAL CHAIN RESOLUTION: Watch → Global
        # With Pydantic, this would become: maxlen = watch.resolved_history_snapshot_max_length
        # @computed_field def resolved_history_snapshot_max_length(self) -> Optional[int]:
        #     if self.history_snapshot_max_length: return self.history_snapshot_max_length
        #     if tag := self._get_override_tag(): return tag.history_snapshot_max_length
        #     return self._datastore.settings.history_snapshot_max_length
        maxlen = self.get('history_snapshot_max_length') or self.get_global_setting('application', 'history_snapshot_max_length')

        if maxlen and self.__history_n and self.__history_n > maxlen:
            self.history_trim(newest_n_items=maxlen)

        # @todo bump static cache of the last timestamp so we dont need to examine the file to set a proper ''viewed'' status
        return snapshot_fname

        extension = None

        # If the caller already resolved the MIME type (e.g. from blob.type or a data URI),
        # use that directly — it's more reliable than guessing from a URL path.
        if mime_type:
            extension = MIME_TO_EXT.get(mime_type.lower().split(';')[0].strip(), None)

        # Fall back to extracting extension from URL path, unless it's a data URI.
        if not extension and url and not url.startswith('data:'):
            try:
                parsed = urlparse(url)
                filename = os.path.basename(parsed.path)
                (_base, ext) = filename.lower().strip().rsplit('.', 1)
                extension = ext
            except ValueError:
                logger.warning(f"UUID: {self.get('uuid')} Cant work out file extension from '{url}', defaulting to ico")

        # Handle data URIs: extract MIME type from the URI itself when not already known
        if not extension and url and url.startswith('data:'):
            m = re.match(r'^data:([^;]+);base64,', url)
            if m:
                extension = MIME_TO_EXT.get(m.group(1).lower(), None)

        if not extension:
            extension = 'ico'

        fname = os.path.join(self.data_dir, f"favicon.{extension}")

        try:
            # validate=True makes sure the string only contains valid base64 chars
            decoded = base64.b64decode(favicon_base_64, validate=True)
        except (binascii.Error, ValueError) as e:
            logger.warning(f"UUID: {self.get('uuid')} FavIcon save data (Base64) corrupt? {str(e)}")
            return None

        if len(decoded) > MAX_FAVICON_BYTES:
            logger.warning(f"UUID: {self.get('uuid')} Favicon too large ({len(decoded)} bytes), skipping")
            return None

        try:
            with open(fname, 'wb') as f:
                f.write(decoded)

            # Invalidate module-level favicon filename cache for this watch
            _FAVICON_FILENAME_CACHE.pop(self.data_dir, None)

            # A signal that could trigger the socket server to update the browser also
            watch_check_update = signal('watch_favicon_bump')
            if watch_check_update:
                watch_check_update.send(watch_uuid=self.get('uuid'))

        except Exception as e:
            logger.warning(f"UUID: {self.get('uuid')} error saving FavIcon to {fname} - {str(e)}")
            return None

        # @todo - Store some checksum and only write when its different
        logger.debug(f"UUID: {self.get('uuid')} updated favicon to at {fname}")

    def get_favicon_filename(self) -> str | None:
        """
        Find any favicon.* file in the watch data directory.

        Uses a module-level cache keyed by data_dir to survive Watch object recreation,
        deepcopy (which drops instance attrs), and concurrent request races.
        Invalidated when a favicon is saved or the watch history is cleared.

        Returns:
            str: Basename of the favicon file, or None if not found.
        """
        if self.data_dir in _FAVICON_FILENAME_CACHE:
            return _FAVICON_FILENAME_CACHE[self.data_dir]

        import glob
        files = glob.glob(os.path.join(self.data_dir, "favicon.*"))
        fname = os.path.basename(files[0]) if files else None
        _FAVICON_FILENAME_CACHE[self.data_dir] = fname
        return fname

