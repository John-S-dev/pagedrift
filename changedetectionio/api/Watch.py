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


def validate_time_schedule_limit(json_data):
    """
    Validate the optional timezone inside time_schedule_limit.

    The edit form runs validateTimeZoneName on this field, but the API did not -
    the OpenAPI schema for time_schedule_limit does not declare a `timezone`
    property at all and does not set additionalProperties:false, so any string
    passed straight through and was stored.

    That matters because the scheduler resolves it with arrow.now(tz), which
    raises on an unknown zone. Before the ticker thread was hardened, a single
    authenticated PUT with a bogus timezone stopped scheduling for EVERY watch
    on the instance. It is now contained to the one watch, but that watch would
    still silently never be checked again, so reject it at the boundary.

    Returns None if valid, or an error message string if invalid.
    """
    schedule = json_data.get('time_schedule_limit')
    if not isinstance(schedule, dict):
        return None

    tz_name = schedule.get('timezone')
    if not tz_name:
        return None

    if not isinstance(tz_name, str):
        return "time_schedule_limit.timezone must be a string IANA timezone name, e.g. 'Europe/Berlin'."

    from zoneinfo import available_timezones
    if tz_name.strip() not in available_timezones():
        return (f"time_schedule_limit.timezone '{tz_name}' is not a valid timezone name. "
                f"Use an IANA name such as 'Europe/Berlin' or 'UTC'.")

    return None


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


class Watch(Resource):
    def __init__(self, **kwargs):
        # datastore is a black box dependency
        self.datastore = kwargs['datastore']
        self.update_q = kwargs['update_q']

    # Get information about a single watch, excluding the history list (can be large)
    # curl http://localhost:5000/api/v1/watch/<uuid_str:uuid>
    # @todo - version2 - ?muted and ?paused should be able to be called together, return the watch struct not "OK"
    # ?recheck=true
    @auth.check_token
    @validate_openapi_request('getWatch')
    def get(self, uuid):
        """Get information about a single watch, recheck, pause, or mute."""
        # Get watch reference first (for pause/mute operations)
        watch_obj = self.datastore.data['watching'].get(uuid)
        if not watch_obj:
            abort(404, message='No watch exists with the UUID of {}'.format(uuid))

        # Create a dict copy for JSON response (with lock for thread safety)
        # This is much faster than deepcopy and doesn't copy the datastore reference
        # WARNING: dict() is a SHALLOW copy - nested dicts are shared with original!
        # Only safe because we only ADD scalar properties (line 97-101), never modify nested dicts
        # If you need to modify nested dicts, use: from copy import deepcopy; watch = deepcopy(dict(watch_obj))
        with self.datastore.lock:
            watch = dict(watch_obj)

        if request.args.get('recheck'):
            worker_pool.queue_item_async_safe(self.update_q, queuedWatchMetaData.PrioritizedItem(priority=1, item={'uuid': uuid}))
            return "OK", 200
        if request.args.get('paused', '') == 'paused':
            watch_obj.pause()
            watch_obj.commit()
            return "OK", 200
        elif request.args.get('paused', '') == 'unpaused':
            watch_obj.unpause()
            watch_obj.commit()
            return "OK", 200
        if request.args.get('muted', '') == 'muted':
            watch_obj.mute()
            watch_obj.commit()
            return "OK", 200
        elif request.args.get('muted', '') == 'unmuted':
            watch_obj.unmute()
            watch_obj.commit()
            return "OK", 200

        # Return without history, get that via another API call
        # Properties are not returned as a JSON, so add the required props manually
        watch['history_n'] = watch_obj.history_n
        # attr .last_changed will check for the last written text snapshot on change
        watch['last_changed'] = watch_obj.last_changed
        watch['viewed'] = watch_obj.viewed
        watch['link'] = watch_obj.link
        watch['open_link'] = watch_obj.open_link

        # Resolved processor config: tag override wins over watch-level config (mirrors restock processor logic)
        import json
        _restock_path = os.path.join(watch_obj.data_dir, 'restock_diff.json') if watch_obj.data_dir else None
        restock_config = {}
        if _restock_path and os.path.isfile(_restock_path):
            try:
                with open(_restock_path, 'r', encoding='utf-8') as _f:
                    restock_config = json.load(_f).get('restock_diff') or {}
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read restock_diff.json for watch {uuid}: {e}")
        restock_source = 'watch'
        tags = self.datastore.data['settings']['application'].get('tags', {})
        for tag_uuid in (watch_obj.get('tags') or []):
            tag = tags.get(tag_uuid, {})
            if tag.get('overrides_watch'):
                restock_config = dict(tag.get('processor_config_restock_diff') or {})
                restock_source = f'tag:{tag_uuid}'
                break
        watch['processor_config_restock_diff'] = restock_config
        watch['processor_config_restock_diff_source'] = restock_source

        # Never expose `__`-prefixed transient/internal fields (e.g. __check_status)
        return strip_internal_api_fields(watch)

    @auth.check_token
    @validate_openapi_request('deleteWatch')
    def delete(self, uuid):
        """Delete a watch and related history."""
        if not self.datastore.data['watching'].get(uuid):
            abort(400, message='No watch exists with the UUID of {}'.format(uuid))

        self.datastore.delete(uuid)
        return 'OK', 204

    @auth.check_token
    @validate_openapi_request('updateWatch')
    def put(self, uuid):
        """Update watch information."""
        watch = self.datastore.data['watching'].get(uuid)
        if not watch:
            abort(404, message='No watch exists with the UUID of {}'.format(uuid))

        if request.json.get('proxy'):
            plist = self.datastore.proxy_list
            if not plist or request.json.get('proxy') not in plist:
                proxy_list_str = ', '.join(plist) if plist else 'none configured'
                return f"Invalid proxy choice, currently supported proxies are '{proxy_list_str}'", 400

        # Validate time_between_check when not using defaults
        validation_error = validate_time_between_check_required(request.json)
        if validation_error:
            return validation_error, 400

        # An invalid timezone here makes the watch permanently unschedulable
        validation_error = validate_time_schedule_limit(request.json)
        if validation_error:
            return validation_error, 400

        # Validate notification_urls if provided
        if 'notification_urls' in request.json:
            from wtforms import ValidationError
            from changedetectionio.api.Notifications import validate_notification_urls
            try:
                notification_urls = request.json.get('notification_urls', [])
                validate_notification_urls(notification_urls)
            except ValidationError as e:
                return str(e), 400

        # XSS etc protection - validate URL if it's being updated
        if 'url' in request.json:
            new_url = request.json.get('url')

            # URL must be a non-empty string
            if new_url is None:
                return "URL cannot be null", 400

            if not isinstance(new_url, str):
                return "URL must be a string", 400

            if not new_url.strip():
                return "URL cannot be empty or whitespace only", 400

            if not is_safe_valid_url(new_url.strip()):
                return "Invalid or unsupported URL format. URL must use http://, https://, or ftp:// protocol", 400

        # Handle processor-config-* fields separately (save to JSON, not datastore)
        from changedetectionio import processors

        # Make a mutable copy of request.json for modification.
        # Silently discard `__`-prefixed transient/internal keys — they are not part of the
        # public schema and must never be writable (e.g. clients that round-trip GET → PUT).
        json_data = strip_internal_api_fields(dict(request.json))

        # Extract and remove processor config fields from json_data
        processor_config_data = processors.extract_processor_config_from_form_data(json_data)

        # Filter out readOnly fields (extracted from OpenAPI spec Watch schema)
        # These are system-managed fields that should never be user-settable
        readonly_fields = get_readonly_watch_fields()

        # Also filter out @property attributes (computed/derived values from the model)
        # These are not stored and should be ignored in PUT requests
        from changedetectionio.model.Watch import model as WatchModel
        property_fields = WatchModel.get_property_names()

        # Combine both sets of fields to ignore
        fields_to_ignore = readonly_fields | property_fields

        # Remove all ignored fields from update data
        for field in fields_to_ignore:
            json_data.pop(field, None)

        # Validate remaining fields - reject truly unknown fields
        # Get valid fields from WatchBase schema
        from . import get_watch_schema_properties
        valid_fields = set(get_watch_schema_properties().keys())

        # Also allow last_viewed (explicitly defined in UpdateWatch schema)
        valid_fields.add('last_viewed')

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


class WatchHistoryDiff(Resource):
    """
    Generate diff between two historical snapshots.

    Note: This API endpoint currently returns text-based diffs and works best
    with the text_json_diff processor. Future processor types (like image_diff,
    restock_diff) may want to implement their own specialized API endpoints
    for returning processor-specific data (e.g., price charts, image comparisons).

    The web UI diff page (/diff/<uuid>) is processor-aware and delegates rendering
    to processors/{type}/difference.py::render() for processor-specific visualizations.
    """
    def __init__(self, **kwargs):
        # datastore is a black box dependency
        self.datastore = kwargs['datastore']

    @auth.check_token
    @validate_openapi_request('getWatchHistoryDiff')
    def get(self, uuid, from_timestamp, to_timestamp):
        """Generate diff between two historical snapshots."""
        from changedetectionio import diff
        from changedetectionio.notification.handler import apply_service_tweaks

        watch = self.datastore.data['watching'].get(uuid)
        if not watch:
            abort(404, message=f"No watch exists with the UUID of {uuid}")

        if not len(watch.history):
            abort(404, message=f"Watch found but no history exists for the UUID {uuid}")

        history_keys = list(watch.history.keys())

        # Handle 'latest' keyword for to_timestamp
        if to_timestamp == 'latest':
            to_timestamp = history_keys[-1]

        # Handle 'previous' keyword for from_timestamp (second-most-recent)
        if from_timestamp == 'previous':
            if len(history_keys) < 2:
                abort(404, message=f"Not enough history entries. Need at least 2 snapshots for 'previous'")
            from_timestamp = history_keys[-2]

        # Validate timestamps exist
        if from_timestamp not in watch.history:
            abort(404, message=f"From timestamp {from_timestamp} not found in watch history")
        if to_timestamp not in watch.history:
            abort(404, message=f"To timestamp {to_timestamp} not found in watch history")

        # Get the format parameter (default to 'text')
        output_format = request.args.get('format', 'text').lower()

        # Validate format
        if output_format not in valid_notification_formats.keys():
            abort(400, message=f"Invalid format. Must be one of: {', '.join(valid_notification_formats.keys())}")

        # Get the word_diff parameter (default to False - line-level mode)
        word_diff = strtobool(request.args.get('word_diff', 'false'))

