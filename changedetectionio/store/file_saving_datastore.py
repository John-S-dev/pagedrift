"""
File-based datastore with individual watch persistence and immediate commits.

This module provides the FileSavingDataStore abstract class that implements:
- Individual watch.json file persistence
- Immediate commit-based persistence (watch.commit(), datastore.commit())
- Atomic file writes safe for NFS/NAS
"""

import json
import os
import tempfile
import time
from loguru import logger

from .base import DataStore
from .. import strtobool

# Try to import orjson for faster JSON serialization
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

# Fsync configuration: Force file data to disk for crash safety
# Default False to match legacy behavior (write-and-rename without fsync)
# Set to True for mission-critical deployments requiring crash consistency
FORCE_FSYNC_DATA_IS_CRITICAL = bool(strtobool(os.getenv('FORCE_FSYNC_DATA_IS_CRITICAL', 'False')))

# ============================================================================
# Helper Functions for Atomic File Operations
# ============================================================================

def save_json_atomic(file_path, data_dict, label="file", max_size_mb=10):
    """
    Save JSON data to disk using atomic write pattern.

    Generic helper for saving any JSON data (settings, watches, etc.) with:
    - Atomic write (temp file + rename)
    - Directory fsync for crash consistency (only for new files)
    - Size validation
    - Proper error handling

    Thread safety: Caller must hold datastore.lock to prevent concurrent modifications.
    Multi-process safety: Not supported - run only one app instance per datastore.

    Args:
        file_path: Full path to target JSON file
        data_dict: Dictionary to serialize
        label: Human-readable label for error messages (e.g., "watch", "settings")
        max_size_mb: Maximum allowed file size in MB

    Raises:
        ValueError: If serialized data exceeds max_size_mb
        OSError: If disk is full (ENOSPC) or other I/O error
    """
    # Check if file already exists (before we start writing)
    # Directory fsync only needed for NEW files to persist the filename
    file_exists = os.path.exists(file_path)

    # Ensure parent directory exists
    parent_dir = os.path.dirname(file_path)
    os.makedirs(parent_dir, exist_ok=True)

    # Create temp file in same directory (required for NFS atomicity)
    fd, temp_path = tempfile.mkstemp(
        suffix='.tmp',
        prefix='json-',
        dir=parent_dir,
        text=False
    )

    fd_closed = False
    try:
        # Serialize data
        t0 = time.time()
        if HAS_ORJSON:
            data = orjson.dumps(data_dict, option=orjson.OPT_INDENT_2)
        else:
            data = json.dumps(data_dict, indent=2, ensure_ascii=False).encode('utf-8')
        serialize_ms = (time.time() - t0) * 1000

        # Safety check: validate size
        MAX_SIZE = max_size_mb * 1024 * 1024
        data_size = len(data)
        if data_size > MAX_SIZE:
            raise ValueError(
                f"{label.capitalize()} data is unexpectedly large: {data_size / 1024 / 1024:.2f}MB "
                f"(max: {max_size_mb}MB). This indicates a bug or data corruption."
            )

        # Write to temp file
        t1 = time.time()
        os.write(fd, data)
        write_ms = (time.time() - t1) * 1000

        # Optional fsync: Force file data to disk for crash safety
        # Only if FORCE_FSYNC_DATA_IS_CRITICAL=True (default: False, matches legacy behavior)
        t2 = time.time()
        if FORCE_FSYNC_DATA_IS_CRITICAL:
            os.fsync(fd)
        file_fsync_ms = (time.time() - t2) * 1000

        os.close(fd)
        fd_closed = True

        # Atomic rename
        t3 = time.time()
        os.replace(temp_path, file_path)
        rename_ms = (time.time() - t3) * 1000

        # Sync directory to ensure filename metadata is durable
        # OPTIMIZATION: Only needed for NEW files. Existing files already have
        # directory entry persisted, so we only need file fsync for data durability.
        dir_fsync_ms = 0
        if not file_exists:
            try:
                dir_fd = os.open(parent_dir, os.O_RDONLY)
                try:
                    t4 = time.time()
                    os.fsync(dir_fd)
                    dir_fsync_ms = (time.time() - t4) * 1000
                finally:
                    os.close(dir_fd)
            except (OSError, AttributeError):
                # Windows doesn't support fsync on directories
                pass

        # Log timing breakdown for slow saves
#        total_ms = serialize_ms + write_ms + file_fsync_ms + rename_ms + dir_fsync_ms
#        if total_ms:  # Log if save took more than 10ms
#            file_status = "new" if not file_exists else "update"
#            logger.trace(
#                f"Save timing breakdown ({total_ms:.1f}ms total, {file_status}): "
#                f"serialize={serialize_ms:.1f}ms, write={write_ms:.1f}ms, "
#                f"file_fsync={file_fsync_ms:.1f}ms, rename={rename_ms:.1f}ms, "
#                f"dir_fsync={dir_fsync_ms:.1f}ms, using_orjson={HAS_ORJSON}"
#            )

    except OSError as e:
        # Cleanup temp file
        if not fd_closed:
            try:
                os.close(fd)
            except:
                pass
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass

        # Provide helpful error messages
        if e.errno == 28:  # ENOSPC
            raise OSError(f"Disk full: Cannot save {label}") from e
        elif e.errno == 122:  # EDQUOT
            raise OSError(f"Disk quota exceeded: Cannot save {label}") from e
        else:
            raise OSError(f"I/O error saving {label}: {e}") from e

    except Exception as e:
        # Cleanup temp file
        if not fd_closed:
            try:
                os.close(fd)
            except:
                pass
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        raise e


def save_entity_atomic(entity_dir, uuid, entity_dict, filename, entity_type, max_size_mb):
    """
    Save an entity (watch/tag) to disk using atomic write pattern.

    Generic function for saving any watch_base subclass (Watch, Tag, etc.).

    Args:
        entity_dir: Directory for this entity (e.g., /datastore/{uuid})
        uuid: Entity UUID (for logging)
        entity_dict: Dictionary representation of the entity
        filename: JSON filename (e.g., 'watch.json', 'tag.json')
        entity_type: Type label for logging (e.g., 'watch', 'tag')
        max_size_mb: Maximum allowed file size in MB

    Raises:
        ValueError: If serialized data exceeds max_size_mb
        OSError: If disk is full (ENOSPC) or other I/O error
    """
    entity_json = os.path.join(entity_dir, filename)
    save_json_atomic(entity_json, entity_dict, label=f"{entity_type} {uuid}", max_size_mb=max_size_mb)


class _EntityFileMissing:
    """Sentinel: the directory exists but holds no file of this entity type."""
    __slots__ = ()
    def __repr__(self):
        return '<ENTITY_FILE_MISSING>'
    def __bool__(self):
        return False


ENTITY_FILE_MISSING = _EntityFileMissing()


def load_tag_from_file(tag_json, uuid, rehydrate_entity_func, missing_ok=False):
    """
    Load a tag from its JSON file.

    Args:
        tag_json: Path to the tag.json file
        uuid: Tag UUID
        rehydrate_entity_func: Function to convert dict to Tag object
        missing_ok: When True, a missing file returns ENTITY_FILE_MISSING instead of
                    logging. Used by load_all_tags, which walks every datastore
                    subdirectory - most of those are watch dirs, not tags.

    Returns:
        Tag object, ENTITY_FILE_MISSING if absent and missing_ok, else None
    """
    try:
        # See load_watch_from_file: open first, size from the open fd, one syscall.
        try:
            f = open(tag_json, 'rb')
        except (FileNotFoundError, NotADirectoryError):
            if missing_ok:
                return ENTITY_FILE_MISSING
            logger.debug(f"Tag file not found: {tag_json} for tag {uuid}")
            return None

        with f:
            file_size = os.fstat(f.fileno()).st_size
            MAX_TAG_SIZE = 1 * 1024 * 1024  # 1MB
            if file_size > MAX_TAG_SIZE:
                logger.critical(
                    f"CORRUPTED TAG DATA: Tag {uuid} file is unexpectedly large: "
                    f"{file_size / 1024 / 1024:.2f}MB (max: {MAX_TAG_SIZE / 1024 / 1024}MB). "
                    f"File: {tag_json}. This indicates a bug or data corruption. "
                    f"Tag will be skipped."
                )
                return None
            raw = f.read()

        tag_data = orjson.loads(raw) if HAS_ORJSON else json.loads(raw.decode('utf-8'))

        tag_data['processor'] = 'restock_diff'
        # Rehydrate tag (convert dict to Tag object)
        # processor_override is set inside the rehydration function
        tag_obj = rehydrate_entity_func(uuid, tag_data)
        return tag_obj

    except json.JSONDecodeError as e:
        logger.critical(
            f"CORRUPTED TAG DATA: Failed to parse JSON for tag {uuid}. "
            f"File: {tag_json}. Error: {e}. "
            f"Tag will be skipped and may need manual recovery from backup."
        )
        return None
    except ValueError as e:
        # orjson raises ValueError for invalid JSON
        if "invalid json" in str(e).lower() or HAS_ORJSON:
            logger.critical(
                f"CORRUPTED TAG DATA: Failed to parse JSON for tag {uuid}. "
                f"File: {tag_json}. Error: {e}. "
                f"Tag will be skipped and may need manual recovery from backup."
            )
            return None
        # Re-raise if it's not a JSON parsing error
        raise
    except Exception as e:
        logger.error(f"Failed to load tag {uuid} from {tag_json}: {e}")
        return None


