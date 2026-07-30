#!/usr/bin/env python3
"""PAGE_WATCH_LIMIT - the optional cap on how many watches one instance will hold.

The limit is enforced in datastore.add_watch(), which every add path funnels through, but each
surface has to report it in its own terms: a flash for the UI, a 429 for the API, one flash for
a whole file in the importers, and nothing at all (just a None) where there's no request context.
"""

import json
from flask import url_for
from .util import delete_all_watches


def test_watch_limit_absent_or_junk_means_unlimited(client, live_server, measure_memory_usage, datastore_path, monkeypatch):
    """No env var, an empty one, or an unparseable one all leave the limit switched off."""
    datastore = live_server.app.config['DATASTORE']

    monkeypatch.delenv('PAGE_WATCH_LIMIT', raising=False)
    assert datastore.watch_limit is None
    assert datastore.watch_limit_reached() is False

    # Junk must not block every add, and must not raise
    monkeypatch.setenv('PAGE_WATCH_LIMIT', 'not-a-number')
    assert datastore.watch_limit is None
    assert datastore.watch_limit_reached() is False

    # Set-but-empty is the same as unset
    monkeypatch.setenv('PAGE_WATCH_LIMIT', '')
    assert datastore.watch_limit is None
    assert datastore.watch_limit_reached() is False


