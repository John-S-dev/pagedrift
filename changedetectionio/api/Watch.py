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


def validate_time_between_check_required(json_data):
    """
    Validate that at least one time interval is specified when not using default settings.
    Returns None if valid, or error message string if invalid.
    Defaults to using global settings if time_between_check_use_default is not provided.
    """
    # Default to using global settings if not specified
    use_default = json_data.get('time_between_check_use_default', True)

    # If using default settings, no validation needed
    if use_default:
        return None

    # If not using defaults, check if time_between_check exists and has at least one non-zero value
    time_check = json_data.get('time_between_check')
    if not time_check:
        # No time_between_check provided and not using defaults - this is an error
        return "At least one time interval (weeks, days, hours, minutes, or seconds) must be specified when not using global settings."

    # time_between_check exists, check if it has at least one non-zero value
    if any([
        (time_check.get('weeks') or 0) > 0,
        (time_check.get('days') or 0) > 0,
        (time_check.get('hours') or 0) > 0,
        (time_check.get('minutes') or 0) > 0,
        (time_check.get('seconds') or 0) > 0
    ]):
        return None

    # time_between_check exists but all values are 0 or empty - this is an error
    return "At least one time interval (weeks, days, hours, minutes, or seconds) must be specified when not using global settings."


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


