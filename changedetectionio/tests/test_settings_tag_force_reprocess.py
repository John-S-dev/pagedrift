#!/usr/bin/env python3
"""
Test that changing global settings or tag configurations forces reprocessing.

import os
import time
from flask import url_for
from .util import wait_for_all_checks


def test_settings_change_forces_reprocess(client, live_server, measure_memory_usage, datastore_path):
    """
    Test that changing global settings clears all checksums to force reprocessing.
    """

    # Setup test content
    test_html = """<html>
     <body>
     <p>Test content that stays the same</p>
     </body>
     </html>
    """
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_html)

    test_url = url_for('test_endpoint', _external=True)

    # Add two watches
    datastore = client.application.config.get('DATASTORE')
    uuid1 = datastore.add_watch(url=test_url, extras={'title': 'Watch 1'})
    uuid2 = datastore.add_watch(url=test_url, extras={'title': 'Watch 2'})

    # Unpause watches
    datastore.data['watching'][uuid1]['paused'] = False
    datastore.data['watching'][uuid2]['paused'] = False

    # First check - establishes baseline
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    wait_for_all_checks(client)

    # Verify checksum files were created
    checksum1 = os.path.join(datastore_path, uuid1, 'last-checksum.txt')
    checksum2 = os.path.join(datastore_path, uuid2, 'last-checksum.txt')
    assert os.path.isfile(checksum1), "First check should create checksum file for watch 1"
    assert os.path.isfile(checksum2), "First check should create checksum file for watch 2"

    # Change global settings (any setting will do)
    res = client.post(
        url_for("settings.settings_page"),
        data={
            "application-empty_pages_are_a_change": "",
            "requests-time_between_check-minutes": 180,
            'application-fetch_backend': "html_requests"
        },
        follow_redirects=True
    )
    assert b"Settings updated." in res.data

    # Give it a moment to process
    time.sleep(0.5)

    # Verify ALL checksum files were deleted
    assert not os.path.isfile(checksum1), "Settings change should delete checksum for watch 1"
    assert not os.path.isfile(checksum2), "Settings change should delete checksum for watch 2"

    # Next check should reprocess (not skip) and recreate checksums
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    wait_for_all_checks(client)

    # Verify checksum files were recreated
    assert os.path.isfile(checksum1), "Reprocessing should recreate checksum file for watch 1"
    assert os.path.isfile(checksum2), "Reprocessing should recreate checksum file for watch 2"

    print("✓ Settings change forces reprocessing of all watches")


