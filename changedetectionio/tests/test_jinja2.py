#!/usr/bin/env python3

import time
import arrow
from flask import url_for
from .util import live_server_setup, wait_for_all_checks
from ..jinja2_custom import render


# def test_setup(client, live_server, measure_memory_usage, datastore_path):
   # #  live_server_setup(live_server) # Setup on conftest per function

# If there was only a change in the whitespacing, then we shouldnt have a change detected
def test_jinja2_in_url_query(client, live_server, measure_memory_usage, datastore_path):
    

    # Add our URL to the import page
    test_url = url_for('test_return_query', _external=True)

    # because url_for() will URL-encode the var, but we dont here
    full_url = "{}?{}".format(test_url,
                              "date={% now 'Europe/Berlin', '%Y' %}.{% now 'Europe/Berlin', '%m' %}.{% now 'Europe/Berlin', '%d' %}", )
    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": full_url, "tags": "test"},
        follow_redirects=True
    )
    assert b"Watch added" in res.data
    wait_for_all_checks(client)

    # It should report nothing found (no new 'has-unread-changes' class)
    res = client.get(
        url_for("ui.ui_preview.preview_page", uuid="first"),
        follow_redirects=True
    )
    assert b'date=2' in res.data

# Test for issue #1493 - jinja2-time offset functionality
def test_jinja2_time_offset_in_url_query(client, live_server, measure_memory_usage, datastore_path):
    """Test that jinja2 time offset expressions work in watch URLs (issue #1493)."""

    # Add our URL to the import page with time offset expression
    test_url = url_for('test_return_query', _external=True)

    # Test the exact syntax from issue #1493 that was broken in jinja2-time
    # This should work now with our custom TimeExtension
    full_url = "{}?{}".format(test_url,
                              "timestamp={% now 'utc' - 'minutes=11', '%Y-%m-%d %H:%M' %}", )
    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": full_url, "tags": "test"},
        follow_redirects=True
    )
    assert b"Watch added" in res.data
    wait_for_all_checks(client)

    # Verify the URL was processed correctly (should not have errors)
    res = client.get(
        url_for("ui.ui_preview.preview_page", uuid="first"),
        follow_redirects=True
    )
    # Should have a valid timestamp in the response
    assert b'timestamp=' in res.data
    # Should not have template error
    assert b'Invalid template' not in res.data


# https://techtonics.medium.com/secure-templating-with-jinja2-understanding-ssti-and-jinja2-sandbox-environment-b956edd60456
def test_jinja2_security_url_query(client, live_server, measure_memory_usage, datastore_path):
    # Add our URL to the import page
    test_url = url_for('test_return_query', _external=True)

    full_url = test_url + "?date={{ ''.__class__.__mro__[1].__subclasses__()}}"

    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": full_url, "tags": "test"},
        follow_redirects=True
    )
    assert b"Watch added" not in res.data


def test_timezone(mocker):
    """Verify that timezone is parsed."""

    timezone = 'America/Buenos_Aires'
    currentDate = arrow.now(timezone)
    arrowNowMock = mocker.patch("arrow.now")
    arrowNowMock.return_value = currentDate
    finalRender = render(f"{{% now '{timezone}' %}}")

    assert finalRender == currentDate.strftime('%a, %d %b %Y %H:%M:%S')

