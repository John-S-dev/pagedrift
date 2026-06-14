#!/usr/bin/env python3

import time
from flask import url_for
from .util import live_server_setup, wait_for_all_checks, delete_all_watches
import os

import json
import uuid


def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False


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

