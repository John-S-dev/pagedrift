#!/usr/bin/env python3

import time
from flask import url_for
from .util import live_server_setup, wait_for_all_checks, extract_rss_token_from_UI, get_UUID_for_tag_name, extract_UUID_from_client, delete_all_watches
import os

from ..store import ChangeDetectionStore


def set_modified_response(datastore_path):
    test_return_data = """<html>
       <body>
     Some initial text<br>
     <p id="only-this">Should be REALLY only this</p>
     <br>
     <p id="not-this">And never this</p>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None

def test_setup_group_tag(client, live_server, measure_memory_usage, datastore_path):
    
    set_original_response(datastore_path=datastore_path)

    # Add a tag with some config, import a tag and it should roughly work
    res = client.post(
        url_for("tags.form_tag_add"),
        data={"name": "test-tag"},
        follow_redirects=True
    )
    assert b"Tag added" in res.data
    assert b"test-tag" in res.data

    res = client.post(
        url_for("tags.form_tag_edit_submit", uuid="first"),
        data={"name": "test-tag",
              "include_filters": '#only-this',
              "subtractive_selectors": '#not-this'},
        follow_redirects=True
    )
    assert b"Updated" in res.data
    tag_uuid = get_UUID_for_tag_name(client, name="test-tag")
    res = client.get(
        url_for("tags.form_tag_edit", uuid="first")
    )
    assert b"#only-this" in res.data
    assert b"#not-this" in res.data

    # Tag should be setup and ready, now add a watch

    test_url = url_for('test_endpoint', _external=True)
    res = client.post(
        url_for("imports.import_page"),
        data={"urls": test_url + "?first-imported=1 test-tag, extra-import-tag"},
        follow_redirects=True
    )
    assert b"1 Imported" in res.data

    res = client.get(url_for("watchlist.index"))
    assert b'import-tag' in res.data
    assert b'extra-import-tag' in res.data

    res = client.get(
        url_for("tags.tags_overview_page"),
        follow_redirects=True
    )
    assert b'import-tag' in res.data
    assert b'extra-import-tag' in res.data

    wait_for_all_checks(client)

    res = client.get(url_for("watchlist.index"))
    assert b'Warning, no filters were found' not in res.data

    res = client.get(
        url_for("ui.ui_preview.preview_page", uuid="first"),
        follow_redirects=True
    )
    assert b'Should be only this' in res.data
    assert b'And never this' not in res.data

    res = client.get(
        url_for("ui.ui_edit.edit_page", uuid="first"),
        follow_redirects=True
    )
    # 2307 the UI notice should appear in the placeholder
    assert b'WARNING: Watch has tag/groups set with special filters' in res.data

    # RSS Group tag filter
    # An extra one that should be excluded
    res = client.post(
        url_for("imports.import_page"),
        data={"urls": test_url + "?should-be-excluded=1 some-tag"},
        follow_redirects=True
    )
    assert b"1 Imported" in res.data
    wait_for_all_checks(client)
    set_modified_response(datastore_path=datastore_path)
    res = client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    wait_for_all_checks(client)
    rss_token = extract_rss_token_from_UI(client)
    res = client.get(
        url_for("rss.feed", token=rss_token, tag="extra-import-tag", _external=True),
        follow_redirects=True
    )
    assert b"should-be-excluded" not in res.data
    assert res.status_code == 200
    assert b"first-imported=1" in res.data
    delete_all_watches(client)

