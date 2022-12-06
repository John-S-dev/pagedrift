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


# Hard to just add more live server URLs when one test is already running (I think)
# So we add our test here (was in a different file)
def test_check_notification(client, live_server, measure_memory_usage, datastore_path):
    
    set_original_response(datastore_path=datastore_path)

    # Re 360 - new install should have defaults set
    # Notification UI lives on its own page since the global settings refactor.
    res = client.get(url_for("settings.notifications.apprise"))
    notification_url = url_for('test_notification_endpoint', _external=True).replace('http', 'json')+"?status_code=204"

    assert default_notification_body.encode() in res.data
    assert default_notification_title.encode() in res.data

    #####################
    # Set this up for when we remove the notification from the watch, it should fallback with these details
    res = client.post(
        url_for("settings.notifications.apprise"),
        data={"notification_urls": notification_url,
              "notification_title": "fallback-title "+default_notification_title,
              "notification_body": "fallback-body "+default_notification_body,
              "notification_format": default_notification_format},
        follow_redirects=True
    )

    assert b"Settings updated." in res.data

    res = client.get(url_for("settings.notifications.apprise"))
    for k,v in valid_notification_formats.items():
        if k == USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH:
            continue
        assert f'value="{k}"'.encode() in res.data # Should be by key NOT value
        assert f'value="{v}"'.encode() not in res.data # Should be by key NOT value


    # When test mode is in BASE_URL env mode, we should see this already configured
    env_base_url = os.getenv('BASE_URL', '').strip()
    if len(env_base_url):
        logging.debug(">>> BASE_URL enabled, looking for %s", env_base_url)
        res = client.get(url_for("settings.notifications.apprise"))
        assert bytes(env_base_url.encode('utf-8')) in res.data
    else:
        logging.debug(">>> SKIPPING BASE_URL check")

    # re #242 - when you edited an existing new entry, it would not correctly show the notification settings
    # Add our URL to the import page
    test_url = url_for('test_endpoint', _external=True)
    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": test_url, "tags": ''},
        follow_redirects=True
    )
    assert b"Watch added" in res.data

    # Give the thread time to pick up the first version
    wait_for_all_checks(client)

    # We write the PNG to disk, but a JPEG should appear in the notification
    # Write the last screenshot png
    testimage_png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='


    uuid = next(iter(live_server.app.config['DATASTORE'].data['watching']))
    screenshot_dir = os.path.join(datastore_path, str(uuid))
    os.makedirs(screenshot_dir, exist_ok=True)
    with open(os.path.join(screenshot_dir, 'last-screenshot.png'), 'wb') as f:
        f.write(base64.b64decode(testimage_png))

    # Goto the edit page, add our ignore text
    # Add our URL to the import page

    print (">>>> Notification URL: "+notification_url)

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




