import os
import re
import threading

from changedetectionio.validate_url import is_safe_valid_url
from changedetectionio.favicon_utils import get_favicon_mime_type

from . import auth
from changedetectionio import queuedWatchMetaData, strtobool
from changedetectionio import worker_pool
from flask import request, make_response, send_from_directory
from flask_restful import abort, Resource
from loguru import logger
import copy

from . import validate_openapi_request, get_readonly_watch_fields, strip_internal_api_fields
from ..notification import valid_notification_formats
from ..notification.handler import newline_re



        # Check for unknown fields
        unknown_fields = set(json_data.keys()) - valid_fields
        if unknown_fields:
            return f"Unknown field(s): {', '.join(sorted(unknown_fields))}", 400

        # Update watch with regular (non-processor-config) fields
        watch.update(json_data)
        watch.commit()

        # Save processor config to JSON file
        processors.save_processor_config(self.datastore, uuid, processor_config_data)

        return "OK", 200


