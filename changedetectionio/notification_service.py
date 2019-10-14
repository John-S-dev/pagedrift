#!/usr/bin/env python3

"""
Notification Service Module
Extracted from update_worker.py to provide standalone notification functionality
for both sync and async workers
"""
import datetime

import pytz
from loguru import logger
import time

from changedetectionio.notification import default_notification_format, valid_notification_formats


def _check_cascading_vars(datastore, var_name, watch):
    """
    Check notification variables in cascading priority:
    Individual watch settings > Tag settings > Global settings
    """
    from changedetectionio.notification import (
        USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH,
        default_notification_body,
        default_notification_title
    )

    # Would be better if this was some kind of Object where Watch can reference the parent datastore etc
    v = watch.get(var_name)
    if v and not watch.get('notification_muted'):
        if var_name == 'notification_format' and v == USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH:
            return datastore.data['settings']['application'].get('notification_format') or default_notification_format

        return v

    tags = datastore.get_all_tags_for_watch(uuid=watch.get('uuid'))
    if tags:
        for tag_uuid, tag in tags.items():
            v = tag.get(var_name)
            if v and not tag.get('notification_muted'):
                return v

    if datastore.data['settings']['application'].get(var_name):
        return datastore.data['settings']['application'].get(var_name)

    # Otherwise could be defaults
    if var_name == 'notification_format':
        return USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH
    if var_name == 'notification_body':
        return default_notification_body
    if var_name == 'notification_title':
        return default_notification_title

    return None


def watch_will_send_content_changed_notification(datastore, watch):
    """Single source of truth for: will a *content changed* notification actually be
    delivered for this watch?

    This mirrors exactly the decision the worker + send_content_changed_notification()
    make together: the watch must not be muted, and a notification URL must resolve via
    the watch > tag > global cascade. Anything that wants to know "is a notification
    going to fire?" (e.g. the worker deciding whether to spend tokens pre-computing the
    LLM change summary that fills the notification body) should ask here, so the answer
    can never drift from what actually gets sent.
    """
    if not watch or watch.get('notification_muted'):
        return False
    return bool(_check_cascading_vars(datastore, 'notification_urls', watch))


class FormattableTimestamp(str):
    """
    A str subclass representing a formatted datetime. As a plain string it renders
    with the default format, but can also be called with a custom format argument
    in Jinja2 templates:

        {{ change_datetime }}                        → '2024-01-15 10:30:00 UTC'
        {{ change_datetime(format='%Y') }}           → '2024'
        {{ change_datetime(format='%A') }}           → 'Monday'
        {{ change_datetime(format='%Y-%m-%d') }}     → '2024-01-15'

    Being a str subclass means it is natively JSON serializable.
    """
    _DEFAULT_FORMAT = '%Y-%m-%d %H:%M:%S %Z'

    def __new__(cls, timestamp):
        dt = datetime.datetime.fromtimestamp(int(timestamp), tz=pytz.UTC)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        dt_local = dt.astimezone(local_tz)
        try:
            formatted = dt_local.strftime(cls._DEFAULT_FORMAT)
        except Exception:
            formatted = dt_local.isoformat()
        instance = super().__new__(cls, formatted)
        instance._dt = dt_local
        return instance

    def __call__(self, format=_DEFAULT_FORMAT):
        try:
            return self._dt.strftime(format)
        except Exception:
            return self._dt.isoformat()


class FormattableExtract(str):
    """
    A str subclass that holds only the extracted changed fragments from a diff.
    Used for {{diff_changed_from}} and {{diff_changed_to}} tokens.

        {{ diff_changed_from }}   → old value(s) only, e.g. "$99.99"
        {{ diff_changed_to }}     → new value(s) only, e.g. "$109.99"

    Multiple changed fragments are joined with newlines.
    Being a str subclass means it is natively JSON serializable.
    """
    def __new__(cls, prev_snapshot, current_snapshot, extract_fn, escape_output=False):
        if prev_snapshot or current_snapshot:
            from changedetectionio import diff as diff_module
            # word_diff=True is required — placemarker extraction regexes only exist in word-diff output
            raw = diff_module.render_diff(prev_snapshot or '', current_snapshot or '', word_diff=True)
            extracted = extract_fn(raw)
        else:
            extracted = ''
        if escape_output and extracted:
            # Placemarkers (@removed_PLACEMARKER_OPEN etc) contain no HTML chars,
            # so html_escape leaves them intact — they still get swapped to <span>
            # tags later by apply_service_tweaks. See GHSA-q8xq-qg4x-wphg.
            from markupsafe import escape as html_escape
            extracted = str(html_escape(extracted))
        instance = super().__new__(cls, extracted)
        return instance


