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

