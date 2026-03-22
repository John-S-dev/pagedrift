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


