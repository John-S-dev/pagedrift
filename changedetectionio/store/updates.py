"""
Schema update migrations for the datastore.

This module contains all schema version upgrade methods (update_1 through update_N).
These are mixed into ChangeDetectionStore to keep the main store file focused.

IMPORTANT: Each update could be run even when they have a new install and the schema is correct.
Therefore - each `update_n` should be very careful about checking if it needs to actually run.
"""

import os
import re
import shutil
import tarfile
import time
from loguru import logger
from copy import deepcopy


# Try to import orjson for faster JSON serialization
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

from ..html_tools import TRANSLATE_WHITESPACE_TABLE
from ..processors.restock_diff import Restock, get_price_from_history_str
from ..blueprint.rss import RSS_CONTENT_FORMAT_DEFAULT
from ..model import USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH

def create_backup_tarball(datastore_path, update_number):
    """
    Create a tarball backup of the entire datastore structure before running an update.

    Includes:
    - All {uuid}/watch.json files
    - All {uuid}/tag.json files
    - changedetection.json (settings, if it exists)
    - url-watches.json (legacy format, if it exists)
    - Directory structure preserved

    Args:
        datastore_path: Path to datastore directory
        update_number: Update number being applied

    Returns:
        str: Path to created tarball, or None if backup failed

    Restoration:
    To restore from a backup:
        cd /path/to/datastore
        tar -xzf before-update-N-timestamp.tar.gz
    This will restore all watch.json and tag.json files and settings to their pre-update state.
    """
    timestamp = int(time.time())
    backup_filename = f"before-update-{update_number}-{timestamp}.tar.gz"
    backup_path = os.path.join(datastore_path, backup_filename)

    try:
        logger.info(f"Creating backup tarball: {backup_filename}")

        with tarfile.open(backup_path, "w:gz") as tar:
            # Backup changedetection.json if it exists (new format)
            changedetection_json = os.path.join(datastore_path, "changedetection.json")
            if os.path.isfile(changedetection_json):
                tar.add(changedetection_json, arcname="changedetection.json")
                logger.debug("Added changedetection.json to backup")

            # Backup url-watches.json if it exists (legacy format)
            url_watches_json = os.path.join(datastore_path, "url-watches.json")
            if os.path.isfile(url_watches_json):
                tar.add(url_watches_json, arcname="url-watches.json")
                logger.debug("Added url-watches.json to backup")

            # Backup all watch/tag directories with their JSON files
            # This preserves the UUID directory structure
            watch_count = 0
            tag_count = 0
            for entry in os.listdir(datastore_path):
                entry_path = os.path.join(datastore_path, entry)

                # Skip if not a directory
                if not os.path.isdir(entry_path):
                    continue

                # Skip hidden directories and backup directories
                if entry.startswith('.') or entry.startswith('before-update-'):
                    continue

                # Backup watch.json if exists
                watch_json = os.path.join(entry_path, "watch.json")
                if os.path.isfile(watch_json):
                    tar.add(watch_json, arcname=f"{entry}/watch.json")
                    watch_count += 1

                    if watch_count % 100 == 0:
                        logger.debug(f"Backed up {watch_count} watch.json files...")

                # Backup tag.json if exists
                tag_json = os.path.join(entry_path, "tag.json")
                if os.path.isfile(tag_json):
                    tar.add(tag_json, arcname=f"{entry}/tag.json")
                    tag_count += 1

            logger.success(f"Backup created: {backup_filename} ({watch_count} watches from disk, {tag_count} tags from disk)")
            return backup_path

    except Exception as e:
        logger.error(f"Failed to create backup tarball: {e}")
        # Try to clean up partial backup
        if os.path.exists(backup_path):
            try:
                os.unlink(backup_path)
            except:
                pass
        return None


class DatastoreUpdatesMixin:
    """
    Mixin class containing all schema update methods.

            if current_schema_version is None:
                # No schema version found - could be a fresh install or very old datastore
                # If this is a fresh/new config with no watches, assume it's up-to-date
                # and set to latest update number (no updates needed)
                if len(self.data['watching']) == 0:
                    # Get the highest update number from available update methods
                    latest_update = updates_available[-1] if updates_available else 0
                    logger.info(f"No schema version found and no watches exist - assuming fresh install, setting schema_version to {latest_update}")
                    self.data['settings']['application']['schema_version'] = latest_update
                    self.commit()
                    return  # No updates needed for fresh install
                else:
                    # Has watches but no schema version - likely old datastore, run all updates
                    logger.warning("No schema version found but watches exist - running all updates from version 0")
                    current_schema_version = 0

        logger.info(f"Current schema version: {current_schema_version}")

        updates_ran = []

        for update_n in updates_available:
            if update_n > current_schema_version:
                logger.critical(f"Applying update_{update_n}")

                # Create tarball backup of entire datastore structure
                # This includes all watch.json files, settings, and preserves directory structure
                backup_path = create_backup_tarball(self.datastore_path, update_n)
                if backup_path:
                    logger.info(f"Backup created at: {backup_path}")
                else:
                    logger.warning("Backup creation failed, but continuing with update")

                try:
                    update_method = getattr(self, f"update_{update_n}")()
                except Exception as e:
                    logger.critical(f"Error while trying update_{update_n}")
                    logger.exception(e)
                    sys.exit(1)
                else:
                    # Bump the version
                    self.data['settings']['application']['schema_version'] = update_n
                    self.commit()

                    logger.success(f"Update {update_n} completed")

                    # Track which updates ran
                    updates_ran.append(update_n)

    # ============================================================================
    # Individual Update Methods
    # ============================================================================

    def update_1(self):
        """Convert minutes to seconds on settings and each watch."""
        if self.data['settings']['requests'].get('minutes_between_check'):
            self.data['settings']['requests']['time_between_check']['minutes'] = self.data['settings']['requests']['minutes_between_check']
            # Remove the default 'hours' that is set from the model
            self.data['settings']['requests']['time_between_check']['hours'] = None

        for uuid, watch in self.data['watching'].items():
            if 'minutes_between_check' in watch:
                # Only upgrade individual watch time if it was set
                if watch.get('minutes_between_check', False):
                    self.data['watching'][uuid]['time_between_check']['minutes'] = watch['minutes_between_check']

    def update_2(self):
        """
        Move the history list to a flat text file index.
        Better than SQLite because this list is only appended to, and works across NAS / NFS type setups.
        """
        # @todo test running this on a newly updated one (when this already ran)
        for uuid, watch in self.data['watching'].items():
            history = []

