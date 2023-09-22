"""
Tests for the optional per-watch "Link to Open" (`link_to_open`).

A watch may point at something that is useless in a browser - an API endpoint or an RSS
feed - while the human-readable page lives somewhere else. `link_to_open` stores that page,
and every "go to the site" affordance (watch list, history/preview header, the
{{watch_open_url}} notification token) uses it in preference to the watched URL.
"""

import os

from flask import url_for

from .util import set_original_response, set_modified_response, wait_for_all_checks, \
    wait_for_notification_endpoint_output

OPEN_URL = "https://example.com/the-real-human-page"


def _add_watch(client, test_url):
    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": test_url, "tags": ''},
        follow_redirects=True
    )
    assert b"Watch added" in res.data
    wait_for_all_checks(client)


