#!/usr/bin/env python3
import io
import os
import time

from flask import url_for

from .util import live_server_setup, wait_for_all_checks, delete_all_watches


# def test_setup(client, live_server, measure_memory_usage, datastore_path):
   #  live_server_setup(live_server) # Setup on conftest per function

def test_import(client, live_server, measure_memory_usage, datastore_path):
    # Give the endpoint time to spin up
    wait_for_all_checks(client)

    res = client.post(
        url_for("imports.import_page"),
        data={
            "distill-io": "",
            "urls": """https://example.com
https://example.com tag1
https://example.com tag1, other tag"""
        },
        follow_redirects=True,
    )
    assert b"3 Imported" in res.data
    assert b"tag1" in res.data
    assert b"other tag" in res.data
    delete_all_watches(client)

    # Clear flask alerts
    res = client.get( url_for("watchlist.index"))
    res = client.get( url_for("watchlist.index"))

