#!/usr/bin/env python3

import time
from flask import url_for
from .util import (
    set_original_response,
    set_modified_response,
    live_server_setup,
    wait_for_all_checks, delete_all_watches
)
from loguru import logger

def run_socketio_watch_update_test(client, live_server, password_mode="", datastore_path=""):
    """Test that the socketio emits a watch update event when content changes"""

    # Set up the test server
    set_original_response(datastore_path=datastore_path)


    # Get the SocketIO instance from the app
    from changedetectionio.flask_app import app
    socketio = app.extensions['socketio']

    # Create a test client for SocketIO
    socketio_test_client = socketio.test_client(app, flask_test_client=client)
    if password_mode == "not logged in, should exit on connect":
        assert not socketio_test_client.is_connected(), "Failed to connect to Socket.IO server because it should bounce this connect"
        return

    assert socketio_test_client.is_connected(), "Failed to connect to Socket.IO server"
    print("Successfully connected to Socket.IO server")

    # Add our URL to the import page
    res = client.post(
        url_for("imports.import_page"),
        data={"urls": url_for('test_endpoint', _external=True)},
        follow_redirects=True
    )
    assert b"1 Imported" in res.data

    res = client.get(url_for("watchlist.index"))
    assert url_for('test_endpoint', _external=True).encode() in res.data

    # Wait for initial check to complete
    wait_for_all_checks(client)

    # Clear any initial messages
    socketio_test_client.get_received()

    # Make a change to trigger an update
    set_modified_response(datastore_path=datastore_path)

    # Force recheck
    res = client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    assert b'Queued 1 watch for rechecking.' in res.data

    # Wait for the watch to be checked
    wait_for_all_checks(client)

    has_watch_update = False
    has_unviewed_update = False
    got_general_stats_update = False

    for i in range(10):
        # Get received events
        received = socketio_test_client.get_received()

        if received:
            logger.info(f"Received {len(received)} events after {i+1} seconds")
            for event in received:
                if event['name'] == 'watch_update':
                    has_watch_update = True
                if event['name'] == 'general_stats_update':
                    got_general_stats_update = True

        if has_unviewed_update:
            break

        # Force a recheck every 5 seconds to ensure events are emitted
#        if i > 0 and i % 5 == 0:
#            print(f"Still waiting for events, forcing another recheck...")
#            res = client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
#            assert b'Queued 1 watch for rechecking.' in res.data
#            wait_for_all_checks(client)

