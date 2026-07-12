import json
import os
import time
import re
from flask import url_for
from loguru import logger

from .util import set_original_response, set_modified_response, set_more_modified_response, live_server_setup, wait_for_all_checks, wait_for_notification_endpoint_output
from . util import  extract_UUID_from_client
import logging
import base64

from changedetectionio.notification import (
    default_notification_body,
    default_notification_format,
    default_notification_title, valid_notification_formats
)
from ..diff import HTML_CHANGED_STYLE
from ..model import USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH
from ..notification_service import FormattableTimestamp


    #
    # https://github.com/caronc/apprise/wiki/Notify_Custom_JSON#header-manipulation
    test_notification_url = "hassio://127.0.0.1/longaccesstoken?verify=no&nid={{watch_uuid}}"

    res = client.post(
        url_for("settings.notifications.apprise"),
        data={
              "notification_body": '{ "url" : "{{ watch_url }}", "secret": 444, "somebug": "网站监测 内容更新了", "another": "{{diff|truncate(1500)}}" }',
              "notification_format": default_notification_format,
              "notification_urls": test_notification_url,
              # https://github.com/caronc/apprise/wiki/Notify_Custom_JSON#get-parameter-manipulation
              "notification_title": "New ChangeDetection.io Notification - {{ watch_url }}  {{diff|truncate(200)}} ",
              },
        follow_redirects=True
    )
    assert b'Settings updated' in res.data
    assert '网站监测'.encode() in res.data
    assert b'{{diff|truncate(1500)}}' in res.data
    assert b'{{diff|truncate(200)}}' in res.data




