#!/usr/bin/env python3

import time
from flask import url_for
from .util import live_server_setup, wait_for_all_checks, delete_all_watches
import os

import json
import uuid


def set_original_response(datastore_path):
    test_return_data = """<html>
       <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
     <div id="sametext">Some text thats the same</div>
     <div id="changetext">Some text that will change</div>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None


def set_modified_response(datastore_path):
    test_return_data = """<html>
       <body>
     Some initial text<br>
     <p>which has this one new line</p>
     <br>
     So let's see what happens.  <br>
     <div id="sametext">Some text thats the same</div>
     <div id="changetext">Some text that changes</div>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)

    return None

def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False


# def test_setup(client, live_server, measure_memory_usage, datastore_path):
   #  live_server_setup(live_server) # Setup on conftest per function


def test_api_simple(client, live_server, measure_memory_usage, datastore_path):


    api_key = live_server.app.config['DATASTORE'].data['settings']['application'].get('api_access_token')

    # Create a watch
    set_original_response(datastore_path=datastore_path)

    # Validate bad URL
    test_url = url_for('test_endpoint', _external=True )
    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": "h://xxxxxxxxxom"}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
        follow_redirects=True
    )
    assert res.status_code == 400

    # Create new
    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": test_url, 'tag': "One, Two", "title": "My test URL"}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
        follow_redirects=True
    )

    assert is_valid_uuid(res.json.get('uuid'))
    watch_uuid = res.json.get('uuid')
    assert res.status_code == 201

    wait_for_all_checks(client)

    # Verify its in the list and that recheck worked
    res = client.get(
        url_for("createwatch", tag="OnE"),
        headers={'x-api-key': api_key}
    )
    assert watch_uuid in res.json.keys()
    before_recheck_info = res.json[watch_uuid]

    assert before_recheck_info['last_checked'] != 0

    #705 `last_changed` should be zero on the first check
    assert before_recheck_info['last_changed'] == 0
    assert before_recheck_info['title'] == 'My test URL'
    assert isinstance(before_recheck_info['link'], str), "link must be a plain string, not a tuple or list"
    assert before_recheck_info['link'] == test_url

    # Check the limit by tag doesnt return anything when nothing found
    res = client.get(
        url_for("createwatch", tag="Something else entirely"),
        headers={'x-api-key': api_key}
    )
    assert len(res.json) == 0
    time.sleep(2)
    wait_for_all_checks(client)
    set_modified_response(datastore_path=datastore_path)
    # Trigger recheck of all ?recheck_all=1
    res = client.get(
        url_for("createwatch", recheck_all='1'),
        headers={'x-api-key': api_key},
    )
    wait_for_all_checks(client)

    time.sleep(2)
    # Did the recheck fire?
    res = client.get(
        url_for("createwatch"),
        headers={'x-api-key': api_key},
    )
    after_recheck_info = res.json[watch_uuid]
    assert after_recheck_info['last_checked'] != before_recheck_info['last_checked']
    assert after_recheck_info['last_changed'] != 0

    # #2877 When run in a slow fetcher like playwright etc
    assert after_recheck_info['last_changed'] ==  after_recheck_info['last_checked']

    # Check history index list
    res = client.get(
        url_for("watchhistory", uuid=watch_uuid),
        headers={'x-api-key': api_key},
    )
    watch_history = res.json
    assert len(res.json) == 2, "Should have two history entries (the original and the changed)"

    # Fetch a snapshot by timestamp, check the right one was found
    res = client.get(
        url_for("watchsinglehistory", uuid=watch_uuid, timestamp=list(res.json.keys())[-1]),
        headers={'x-api-key': api_key},
    )
    assert b'which has this one new line' in res.data

    # Fetch a snapshot by 'latest'', check the right one was found
    res = client.get(
        url_for("watchsinglehistory", uuid=watch_uuid, timestamp='latest'),
        headers={'x-api-key': api_key},
    )
    assert b'which has this one new line' in res.data
    assert b'<div id' not in res.data

    time.sleep(3)
    # Fetch the whole watch again, viewed should be true
    res = client.get(
        url_for("watch", uuid=watch_uuid),
        headers={'x-api-key': api_key}
    )
    watch = res.json
    assert watch.get('viewed') == True

    # basic systeminfo check
    res = client.get(
        url_for("systeminfo"),
        headers={'x-api-key': api_key},
    )
    assert res.json.get('watch_count') == 1
    assert res.json.get('uptime') > 0.5

    ######################################################
    # Mute and Pause, check it worked
    res = client.get(
        url_for("watch", uuid=watch_uuid, paused='paused'),
        headers={'x-api-key': api_key}
    )
    assert b'OK' in res.data
    res = client.get(
        url_for("watch", uuid=watch_uuid,  muted='muted'),
        headers={'x-api-key': api_key}
    )
    assert b'OK' in res.data
    res = client.get(
        url_for("watch", uuid=watch_uuid),
        headers={'x-api-key': api_key}
    )
    assert res.json.get('paused') == True
    assert res.json.get('notification_muted') == True

    # Now unpause, unmute
    res = client.get(
        url_for("watch", uuid=watch_uuid,  muted='unmuted'),
        headers={'x-api-key': api_key}
    )
    assert b'OK' in res.data
    res = client.get(
        url_for("watch", uuid=watch_uuid, paused='unpaused'),
        headers={'x-api-key': api_key}
    )
    assert b'OK' in res.data
    res = client.get(
        url_for("watch", uuid=watch_uuid),
        headers={'x-api-key': api_key}
    )
    assert res.json.get('paused') == 0
    assert res.json.get('notification_muted') == 0
    ######################################################





    # Finally delete the watch
    res = client.delete(
        url_for("watch", uuid=watch_uuid),
        headers={'x-api-key': api_key},
    )
    assert res.status_code == 204

    # Check via a relist
    res = client.get(
        url_for("createwatch"),
        headers={'x-api-key': api_key}
    )
    assert len(res.json) == 0, "Watch list should be empty"

def test_api_delete_watch_history(client, live_server, measure_memory_usage, datastore_path):
    """DELETE /api/v1/watch/<uuid>/history should wipe the snapshots but keep the watch (#4397)"""

    api_key = live_server.app.config['DATASTORE'].data['settings']['application'].get('api_access_token')

    set_original_response(datastore_path=datastore_path)
    test_url = url_for('test_endpoint', _external=True)

    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": test_url}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
        follow_redirects=True
    )
    assert res.status_code == 201
    watch_uuid = res.json.get('uuid')
    wait_for_all_checks(client)

    # A second snapshot so we know we're clearing more than one
    set_modified_response(datastore_path=datastore_path)
    client.get(url_for("watch", uuid=watch_uuid, recheck='1'), headers={'x-api-key': api_key})
    wait_for_all_checks(client)

    res = client.get(
        url_for("watchhistory", uuid=watch_uuid),
        headers={'x-api-key': api_key},
    )
    assert len(res.json) == 2, "Should have two history entries before clearing"

    # Unknown watch UUID should 404 and not blow up
    res = client.delete(
        url_for("watchhistory", uuid='4d8b5b4a-8e0b-4d4a-9f57-3f2b1c0d9e11'),
        headers={'x-api-key': api_key},
    )
    assert res.status_code == 404

    # Requires the API key
    res = client.delete(url_for("watchhistory", uuid=watch_uuid))
    assert res.status_code == 403

    # Pause it first - clearing resets last_checked to 0 which otherwise makes the ticker
    # queue an instant recheck, and that would race with the assertions below
    client.get(url_for("watch", uuid=watch_uuid, paused='paused'), headers={'x-api-key': api_key})

    # Now really clear it
    res = client.delete(
        url_for("watchhistory", uuid=watch_uuid),
        headers={'x-api-key': api_key},
    )
    assert res.status_code == 204

    res = client.get(
        url_for("watchhistory", uuid=watch_uuid),
        headers={'x-api-key': api_key},
    )
    assert res.json == {}, "History should be empty after DELETE"

    # The watch itself must survive, with its state reset
    res = client.get(
        url_for("watch", uuid=watch_uuid),
        headers={'x-api-key': api_key}
    )
    assert res.status_code == 200
    assert res.json.get('url') == test_url
    assert res.json.get('history_n') == 0
    assert res.json.get('last_checked') == 0
    assert res.json.get('previous_md5') == False

    # And a snapshot fetch now has nothing to give
    res = client.get(
        url_for("watchsinglehistory", uuid=watch_uuid, timestamp='latest'),
        headers={'x-api-key': api_key},
    )
    assert res.status_code == 404

    delete_all_watches(client)


def test_access_denied(client, live_server, measure_memory_usage, datastore_path):
    # `config_api_token_enabled` Should be On by default
    res = client.get(
        url_for("createwatch")
    )
    assert res.status_code == 403

    res = client.get(
        url_for("createwatch"),
        headers={'x-api-key': "something horrible"}
    )
    assert res.status_code == 403

    # Disable config_api_token_enabled and it should work
    res = client.post(
        url_for("settings.settings_page"),
        data={
            "requests-time_between_check-minutes": 180,
            "application-fetch_backend": "html_requests",
            "application-api_access_token_enabled": ""
        },
        follow_redirects=True
    )

    assert b"Settings updated." in res.data

    res = client.get(
        url_for("createwatch")
    )
    assert res.status_code == 200

    # Cleanup everything
    delete_all_watches(client)

    res = client.post(
        url_for("settings.settings_page"),
        data={
            "requests-time_between_check-minutes": 180,
            "application-fetch_backend": "html_requests",
            "application-api_access_token_enabled": "y"
        },
        follow_redirects=True
    )
    assert b"Settings updated." in res.data

def test_api_watch_PUT_update(client, live_server, measure_memory_usage, datastore_path):

    api_key = live_server.app.config['DATASTORE'].data['settings']['application'].get('api_access_token')
    # Create a watch
    set_original_response(datastore_path=datastore_path)
    test_url = url_for('test_endpoint', _external=True)

    # Create new
    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": test_url,
                         'tag': "One, Two",
                         "title": "My test URL",
                         'headers': {'cookie': 'yum'},
                         "conditions": [
                             {
                                 "field": "page_filtered_text",
                                 "operator": "contains_regex",
                                 "value": "."  # contains anything
                             }
                         ],
                         "conditions_match_logic": "ALL",
                         }
                        ),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
        follow_redirects=True
    )

    if res.status_code != 201:
        print(f"\n=== POST createwatch failed with {res.status_code} ===")
        print(f"Response: {res.data}")
    assert res.status_code == 201

    wait_for_all_checks(client)
    # Get a listing, it will be the first one
    res = client.get(
        url_for("createwatch"),
        headers={'x-api-key': api_key}
    )

    watch_uuid = list(res.json.keys())[0]
    assert not res.json[watch_uuid].get('viewed'), 'A newly created watch can only be unviewed'

    # Check in the edit page just to be sure
    res = client.get(
        url_for("ui.ui_edit.edit_page", uuid=watch_uuid),
    )
    assert b"cookie: yum" in res.data, "'cookie: yum' found in 'headers' section"
    assert b"One" in res.data, "Tag 'One' was found"
    assert b"Two" in res.data, "Tag 'Two' was found"

