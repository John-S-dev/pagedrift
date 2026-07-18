import time
from flask import url_for
from email import message_from_string
from email.policy import default as email_policy

from changedetectionio.diff import HTML_REMOVED_STYLE, HTML_ADDED_STYLE, HTML_CHANGED_STYLE, REMOVED_PLACEMARKER_OPEN, \
    CHANGED_PLACEMARKER_OPEN, ADDED_PLACEMARKER_OPEN
from changedetectionio.notification_service import NotificationContextData
from changedetectionio.tests.util import set_original_response, set_modified_response, set_more_modified_response, live_server_setup, \
    wait_for_all_checks, \
    set_longer_modified_response, delete_all_watches

import logging
import os

# NOTE - RELIES ON mailserver as hostname running, see github build recipes
smtp_test_server = os.getenv('SMTP_TEST_MAILSERVER', 'mailserver')

ALL_MARKUP_TOKENS = ''.join(f"TOKEN: '{t}'\n{{{{{t}}}}}\n" for t in NotificationContextData().keys())

def test_check_notification_plaintext_format(client, live_server, measure_memory_usage, datastore_path):
    set_original_response(datastore_path=datastore_path)


    notification_url = f'mailto://changedetection@{smtp_test_server}:11025/?to=fff@home.com'

    #####################
    # Set this up for when we remove the notification from the watch, it should fallback with these details
    res = client.post(
        url_for("settings.notifications.apprise"),
        data={"notification_urls": notification_url,
              "notification_title": "fallback-title {{watch_title}}  {{ diff_added.splitlines()[0] if diff_added else 'diff added didnt split' }}  " + default_notification_title,
              "notification_body": f"some text\n" + default_notification_body + f"\nMore output test\n{ALL_MARKUP_TOKENS}",
              "notification_format": 'text'},
        follow_redirects=True
    )

    assert b"Settings updated." in res.data

    # Add a watch and trigger a HTTP POST
    test_url = url_for('test_endpoint', _external=True)
    uuid = client.application.config.get('DATASTORE').add_watch(url=test_url)
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    time.sleep(2)

    set_longer_modified_response(datastore_path=datastore_path)
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    wait_for_all_checks(client)

    time.sleep(3)

    msg_raw = get_last_message_from_smtp_server()
    assert len(msg_raw) >= 1
    #time.sleep(60)
    # Parse the email properly using Python's email library
    msg = message_from_string(msg_raw, policy=email_policy)
    # Subject/title got marked up
    subject = msg['subject']
    # Subject should always be plaintext and never marked up to anything else
    assert REMOVED_PLACEMARKER_OPEN not in subject
    assert CHANGED_PLACEMARKER_OPEN not in subject
    assert ADDED_PLACEMARKER_OPEN not in subject
    assert 'diff added didnt split' not in subject
    assert '(changed) Which is across' in subject
    assert 'PLACEMARKER' not in subject

    # The email should be plain text only (not multipart)
    assert not msg.is_multipart()
    assert msg.get_content_type() == 'text/plain'

    # Get the plain text content
    text_content = msg.get_content()
    assert '(added) So let\'s see what happens.\r\n' in text_content  # The plaintext part

    # Should NOT contain HTML
    assert '<br>' not in text_content  # We should not have HTML in plain text
    delete_all_watches(client)



