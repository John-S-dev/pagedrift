import shutil

from changedetectionio.strtobool import strtobool

from changedetectionio.validate_url import is_safe_valid_url

from flask import (
    flash,
    has_request_context
)
from flask_babel import gettext

from ..model import App, Watch
from copy import deepcopy
from os import path, unlink
import json
import os
import re
import secrets
import sys
import time
import uuid as uuid_builder
from loguru import logger
from blinker import signal

from ..model.Tags import TagsDict

# Try to import orjson for faster JSON serialization
try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

from ..processors import get_custom_watch_obj_for_processor, find_processors

# Import the base class and helpers
from .file_saving_datastore import (FileSavingDataStore, load_all_watches, load_all_tags, load_watch_from_file,
                                    save_json_atomic)
from .updates import DatastoreUpdatesMixin

# Because the server will run as a daemon and wont know the URL for notification links when firing off a notification
BASE_URL_NOT_SET_TEXT = '("Base URL" not set - see settings - notifications)'

dictfilt = lambda x, y: dict([(i, x[i]) for i in x if i in set(y)])


# Is there an existing library to ensure some data store (JSON etc) is in sync with CRUD methods?
# Open a github issue if you know something :)
# https://stackoverflow.com/questions/6190468/how-to-trigger-function-on-value-change
_TAG_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


class ChangeDetectionStore(DatastoreUpdatesMixin, FileSavingDataStore):
    __version_check = True

    def __init__(self, datastore_path="/datastore", include_default_watches=True, version_tag="0.0.0"):
        # Initialize parent class
        super().__init__()

        # Should only be active for docker
        # logging.basicConfig(filename='/dev/stdout', level=logging.INFO)
        self.datastore_path = datastore_path
        self.start_time = time.time()
        self.save_version_copy_json_db(version_tag)
        self.reload_state(datastore_path=datastore_path, include_default_watches=include_default_watches, version_tag=version_tag)

    def save_version_copy_json_db(self, version_tag):
        """
        Create version-tagged backup of changedetection.json.

        This is called on version upgrades to preserve a backup in case
        the new version has issues.
        """
        import re

    def _rehydrate_watches(self):
        """Rehydrate watch entities from stored data (converts dicts to Watch objects)."""
        watch_count = len(self.__data.get('watching', {}))
        if watch_count == 0:
            return

        logger.info(f"Rehydrating {watch_count} watches...")
        watching_rehydrated = {}
        for uuid, watch_dict in self.__data.get('watching', {}).items():
            if isinstance(watch_dict, dict):
                watching_rehydrated[uuid] = self.rehydrate_entity(uuid, watch_dict)
            else:
                logger.error(f"Watch UUID {uuid} already rehydrated")

        self.__data['watching'] = watching_rehydrated
        logger.success(f"Rehydrated {watch_count} watches into Watch objects")


    def _load_state(self, main_settings_filename="changedetection.json"):
        """
        Load complete datastore state from storage.

        Orchestrates loading of settings, watches, and tags using polymorphic methods.
        """
        # Load settings
        settings_data = self._load_settings(filename=main_settings_filename)
        self._apply_settings(settings_data)

        # Load watches, scan them from the disk
        self._load_watches()
        self._rehydrate_watches()

        # Load tags from individual tag.json files
        # These will override any tags in settings (migration path)
        self._load_tags()

        # Rehydrate any remaining tags from settings (legacy/fallback)
        self._rehydrate_tags()

    def reload_state(self, datastore_path, include_default_watches, version_tag):
        """
        Load datastore from storage or create new one.

        Supports two scenarios:
        1. NEW format: changedetection.json exists → load and run updates if needed
        2. EMPTY: No changedetection.json → create new OR trigger migration from legacy

        Note: Legacy url-watches.json migration happens in update_26, not here.
        """
        logger.info(f"Datastore path is '{datastore_path}'")

        # CRITICAL: Update datastore_path (was using old path from __init__)
        self.datastore_path = datastore_path

        # Initialize data structure
        self.__data = App.model(datastore_path=datastore_path)
        self.json_store_path = os.path.join(self.datastore_path, "changedetection.json")

        # Base definition for all watchers (deepcopy part of #569)
        self.generic_definition = deepcopy(Watch.model(datastore_path=datastore_path, __datastore=self.__data, default={}))

        # Validate proxies.json if it exists
        _ = self.proxy_list  # Just to test parsing

        # Ensure app_guid exists (for datastores loaded from existing files)
        if 'app_guid' not in self.__data:
            if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
                self.__data['app_guid'] = "test-" + str(uuid_builder.uuid4())
            else:
                self.__data['app_guid'] = str(uuid_builder.uuid4())
            self.commit()

        # Ensure RSS access token exists
        if not self.__data['settings']['application'].get('rss_access_token'):
            secret = secrets.token_hex(16)
            self.__data['settings']['application']['rss_access_token'] = secret
            self.commit()

        # Ensure API access token exists
        if not self.__data['settings']['application'].get('api_access_token'):
            secret = secrets.token_hex(16)
            self.__data['settings']['application']['api_access_token'] = secret
            self.commit()

        # Handle password reset lockfile
        password_reset_lockfile = os.path.join(self.datastore_path, "removepassword.lock")
        if path.isfile(password_reset_lockfile):
            self.remove_password()
            unlink(password_reset_lockfile)

    def rehydrate_entity(self, uuid, entity, processor_override=None):
        """Set the dict back to the dict Watch object"""
        entity['uuid'] = uuid

        if processor_override:
            watch_class = get_custom_watch_obj_for_processor(processor_override)
            entity['processor'] = processor_override
        else:
            watch_class = get_custom_watch_obj_for_processor(entity.get('processor'))

        if entity.get('processor') != 'text_json_diff':
            logger.trace(f"Loading Watch object '{watch_class.__module__}.{watch_class.__name__}' for UUID {uuid}")

        entity = watch_class(datastore_path=self.datastore_path, __datastore=self.__data, default=entity)
        return entity

    # ============================================================================
    # FileSavingDataStore Abstract Method Implementations
    # ============================================================================

    def _watch_exists(self, uuid):
        """Check if watch exists in datastore."""
        return uuid in self.__data['watching']

    def _get_watch_dict(self, uuid):
        """Get watch as dictionary."""
        return dict(self.__data['watching'][uuid])

    def _build_settings_data(self):
        """
        Build settings data structure for saving.

        Tags behavior depends on schema version:
        - Before update_28 (schema < 28): Tags saved in settings for migration
        - After update_28 (schema >= 28): Tags excluded from settings (in individual files)

        Returns:
            dict: Settings data ready for serialization
        """
        import copy

        # Deep copy settings to avoid modifying the original
        settings_copy = copy.deepcopy(self.__data['settings'])

        # Is saved as {uuid}/tag.json
        settings_copy['application']['tags'] = {}

        return {
            'note': 'Settings file - watches are in {uuid}/watch.json, tags are in {uuid}/tag.json',
            'app_guid': self.__data.get('app_guid'),
            'settings': settings_copy,
            'build_sha': self.__data.get('build_sha'),
            'version_tag': self.__data.get('version_tag')
        }

    def _save_settings(self):
        """
        Save settings to storage.

        File backend implementation: saves to changedetection.json
        Implementation of abstract method from FileSavingDataStore.
        Uses the generic save_json_atomic helper.

        Raises:
            OSError: If disk is full or other I/O error
        """
        settings_data = self._build_settings_data()
        changedetection_json = os.path.join(self.datastore_path, "changedetection.json")
        save_json_atomic(changedetection_json, settings_data, label="settings")

    def _load_watches(self):
        """
        Load all watches from storage.

        File backend implementation: reads individual watch.json files
        Implementation of abstract method from FileSavingDataStore.
        Delegates to helper function and stores results in internal data structure.
        """

        # Store loaded data
        # @note this will also work for the old legacy format because self.__data['watching'] should already have them loaded by this point.
        self.__data['watching'].update(load_all_watches(
            self.datastore_path,
            self.rehydrate_entity
        ))
        logger.debug(f"Loaded {len(self.__data['watching'])} watches")

    def _load_tags(self):
        """
        Load all tags from storage.

        File backend implementation: reads individual tag.json files.
        Tags loaded from files override any tags in settings (migration path).
        """
        from ..model import Tag

        def rehydrate_tag(uuid, entity_dict):
            """Rehydrate tag as Tag object with forced restock_diff processor."""
            entity_dict['uuid'] = uuid
            entity_dict['processor'] = 'restock_diff'  # Force processor for override functionality

            return Tag.model(
                datastore_path=self.datastore_path,
                __datastore=self.__data,
                default=entity_dict
            )

        tags = load_all_tags(
            self.datastore_path,
            rehydrate_tag
        )

        Returns:
            int: Number of checksum files deleted
        """
        deleted_count = 0
        for uuid, watch in self.__data['watching'].items():
            if watch.get('tags') and tag_uuid in watch['tags']:
                if watch.data_dir:
                    checksum_file = os.path.join(watch.data_dir, 'last-checksum.txt')
                    if os.path.isfile(checksum_file):
                        try:
                            os.remove(checksum_file)
                            deleted_count += 1
                            logger.debug(f"Cleared checksum for watch {uuid} (tag {tag_uuid})")
                        except OSError as e:
                            logger.warning(f"Failed to delete checksum file for {uuid}: {e}")

        logger.info(f"Cleared {deleted_count} checksum files for tag {tag_uuid}")
        return deleted_count

    def commit(self):
        """
        Save settings immediately to disk using atomic write.

        Uses atomic write pattern (temp file + rename) for crash safety.

        Fire-and-forget: Logs errors but does not raise exceptions.
        Settings data remains in memory even if save fails, so next commit will retry.
        """
        try:
            self._save_settings()
            logger.debug("Committed settings")
        except Exception as e:
            logger.error(f"Failed to commit settings: {e}")

    def update_watch(self, uuid, update_obj):

        # It's possible that the watch could be deleted before update
        if not self.__data['watching'].get(uuid):
            return

        with self.lock:

            # In python 3.9 we have the |= dict operator, but that still will lose data on nested structures...
            for dict_key, d in self.generic_definition.items():
                if isinstance(d, dict):
                    if update_obj is not None and dict_key in update_obj:
                        self.__data['watching'][uuid][dict_key].update(update_obj[dict_key])
                        del (update_obj[dict_key])

            self.__data['watching'][uuid].update(update_obj)

        # Immediate save
        self.__data['watching'][uuid].commit()

    @property
    def threshold_seconds(self):
        seconds = 0
        for m, n in Watch.mtable.items():
            x = self.__data['settings']['requests']['time_between_check'].get(m)
            if x:
                seconds += x * n
        return seconds

    @property
    def unread_changes_count(self):
        unread_changes_count = 0
        for uuid, watch in self.__data['watching'].items():
            if watch.history_n >= 2 and watch.viewed == False:
                unread_changes_count += 1

        return unread_changes_count

    @property
    def data(self):
        # Re #152, Return env base_url if not overriden
        # Re #148 - Some people have just {{ base_url }} in the body or title, but this may break some notification services
        #           like 'Join', so it's always best to atleast set something obvious so that they are not broken.

        Returns:
            bool: True if resource exists
        """
        resource_path = os.path.join(self.datastore_path, watch_uuid, resource_name)
        return path.isfile(resource_path)

    def visualselector_data_is_ready(self, watch_uuid):
        """
        Check if visual selector data (screenshot + elements) is ready.

        Returns:
            bool: True if both screenshot and elements data exist
        """
        has_screenshot = self._watch_resource_exists(watch_uuid, "last-screenshot.png")
        has_elements = self._watch_resource_exists(watch_uuid, "elements.deflate")
        return has_screenshot and has_elements

    # Old sync_to_json and save_datastore methods removed - now handled by FileSavingDataStore parent class

    @property
    def proxy_list(self):
        proxy_list = {}
        proxy_list_file = os.path.join(self.datastore_path, 'proxies.json')

        # Load from external config file
        if path.isfile(proxy_list_file):
            if HAS_ORJSON:
                # orjson.loads() expects UTF-8 encoded bytes #3611
                with open(os.path.join(self.datastore_path, "proxies.json"), 'rb') as f:
                    proxy_list = orjson.loads(f.read())
            else:
                with open(os.path.join(self.datastore_path, "proxies.json"), encoding='utf-8') as f:
                    proxy_list = json.load(f)

        # Mapping from UI config if available
        extras = self.data['settings']['requests'].get('extra_proxies')
        if extras:
            i = 0
            for proxy in extras:
                i += 0
                if proxy.get('proxy_name') and proxy.get('proxy_url'):
                    k = "ui-" + str(i) + proxy.get('proxy_name')
                    proxy_list[k] = {'label': proxy.get('proxy_name'), 'url': proxy.get('proxy_url')}

        if proxy_list and strtobool(os.getenv('ENABLE_NO_PROXY_OPTION', 'True')):
            proxy_list["no-proxy"] = {'label': "No proxy", 'url': ''}

        return proxy_list if len(proxy_list) else None

    def get_preferred_proxy_for_watch(self, uuid):
        """
        Returns the preferred proxy by ID key
        :param uuid: UUID
        :return: proxy "key" id
        """

        if self.proxy_list is None:
            return None

        # If it's a valid one
        watch = self.data['watching'].get(uuid)

        if strtobool(os.getenv('ENABLE_NO_PROXY_OPTION', 'True')) and watch.get('proxy') == "no-proxy":
            return None

        if watch.get('proxy') and watch.get('proxy') in list(self.proxy_list.keys()):
            return watch.get('proxy')

