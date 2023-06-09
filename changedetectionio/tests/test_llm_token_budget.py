#!/usr/bin/env python3
"""
Tests that verify global LLM token budget counters cannot be tampered with
via the API (watch PUT) or via form submissions (settings page POST).

This is critical for hosted deployments where the operator sets
LLM_TOKEN_BUDGET_MONTH in the container — tenants must not be able
to reset or inflate the counter themselves.
"""

import json
import os

import pytest
from flask import url_for

from changedetectionio.tests.util import live_server_setup, delete_all_watches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_token_counters(datastore, this_month=5000, total=12000):
    """Pre-load token counters into the datastore's llm settings dict."""
    from changedetectionio.llm.evaluator import _get_month_key
    app_settings = datastore.data['settings']['application']
    if 'llm' not in app_settings:
        app_settings['llm'] = {}
    app_settings['llm'].update({
        'model': 'gpt-4o-mini',
        'api_key': 'sk-test',
        'tokens_this_month': this_month,
        'tokens_total_cumulative': total,
        'tokens_month_key': _get_month_key(),
    })


def test_api_watch_put_llm_readonly_fields_are_ignored(
        client, live_server, measure_memory_usage, datastore_path):
    """
    llm_prefilter, llm_evaluation_cache, llm_last_tokens_used,
    llm_tokens_used_cumulative are all readOnly in the API spec.
    Sending them in a PUT must not raise an error (they should be silently
    stripped) and must not modify the watch's stored values.
    """
    ds = client.application.config.get('DATASTORE')
    api_key = ds.data['settings']['application'].get('api_access_token')

    test_url = url_for('test_endpoint', _external=True)

    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": test_url}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
        follow_redirects=True,
    )
    assert res.status_code == 201
    uuid = res.json.get('uuid')

    # Try to set readOnly LLM fields via PUT
    res = client.put(
        url_for("watch", uuid=uuid),
        headers={'x-api-key': api_key, 'content-type': 'application/json'},
        data=json.dumps({
            "url": test_url,
            "llm_tokens_used_cumulative": 999999,
            "llm_last_tokens_used": 888888,
            "llm_prefilter": "div.hacked",
            "llm_evaluation_cache": {"fake_key": {"important": True}},
        }),
    )
    # Must succeed (not 400) — readOnly fields are silently stripped
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"

    # Fetch back and confirm readOnly values were NOT stored
    res = client.get(
        url_for("watch", uuid=uuid),
        headers={'x-api-key': api_key},
    )
    assert res.json.get('llm_tokens_used_cumulative') != 999999
    assert res.json.get('llm_last_tokens_used') != 888888

    delete_all_watches(client)


# ---------------------------------------------------------------------------
# Settings form tamper tests
# ---------------------------------------------------------------------------

