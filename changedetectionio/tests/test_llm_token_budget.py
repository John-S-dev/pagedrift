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

def test_settings_form_preserves_token_counters(
        client, live_server, measure_memory_usage, datastore_path):
    """
    Submitting the settings form (POST /settings) must preserve existing
    token counters even when the LLM model/key fields change.
    A malicious or accidental form submission must not zero the counters.
    """
    ds = client.application.config.get('DATASTORE')
    _seed_token_counters(ds, this_month=3000, total=9000)

    before = _get_counters(ds)
    assert before['tokens_this_month'] == 3000

    # Submit settings form with a different model — simulates a normal settings save
    res = client.post(
        url_for('settings.settings_page'),
        data={
            # LLM sub-form fields
            'llm-model': 'gpt-4o',
            'llm-api_key': 'sk-different-key',
            'llm-api_base': '',
            # Minimal required fields to pass form validation
            'application-pager_size': '50',
            'application-notification_format': 'System default',
            'requests-time_between_check-days': '0',
            'requests-time_between_check-hours': '0',
            'requests-time_between_check-minutes': '5',
            'requests-time_between_check-seconds': '0',
            'requests-time_between_check-weeks': '0',
            'requests-workers': '10',
            'requests-timeout': '60',
        },
        follow_redirects=True,
    )
    # Settings save may redirect; we just need it to not crash
    assert res.status_code == 200

    after = _get_counters(ds)
    assert after['tokens_this_month'] == 3000, \
        f"Settings form save must not reset tokens_this_month (got {after['tokens_this_month']})"
    assert after['tokens_total_cumulative'] == 9000, \
        f"Settings form save must not reset tokens_total_cumulative (got {after['tokens_total_cumulative']})"

    delete_all_watches(client)


def test_settings_form_blank_llm_integer_fields_preserve_stored_values(
        client, live_server, measure_memory_usage, datastore_path):
    """
    Empty IntegerField submissions come back as None from WTForms. LLMSettings
    declares token_budget_month / max_input_chars / max_tokens_per_count_period /
    local_token_multiplier as strict `int`, so a None passed through to
    model_validate raises ValidationError and 500s the settings save.

    Regression for settings/__init__.py — the LLM merge must drop None values
    (treat them like absent keys) so blank IntegerField submissions preserve
    the stored value instead of crashing the form.
    """
    ds = client.application.config.get('DATASTORE')
    ds.data['settings']['application']['llm'] = {
        'model': 'gpt-4o',
        'api_key': 'sk-existing',
        'token_budget_month': 50000,
        'max_input_chars': 200000,
        'max_tokens_per_count_period': 1000,
        'local_token_multiplier': 3,
    }

    res = client.post(
        url_for('settings.settings_page'),
        data={
            'llm-model': 'gpt-4o',
            'llm-api_key': '',
            'llm-api_base': '',
            # The bug-trigger: every LLM IntegerField submitted blank
            'llm-token_budget_month': '',
            'llm-max_input_chars': '',
            'llm-max_tokens_per_count_period': '',
            'llm-local_token_multiplier': '',
            # Minimal required fields for the rest of the form to validate.
            # 'System default' is popped from notification_format choices for the
            # global form, so it must be one of the real codes (e.g. 'html').
            'application-pager_size': '50',
            'application-notification_format': 'html',
            'application-fetch_backend': 'html_requests',
            'application-rss_diff_length': '5',
            'application-filter_failure_notification_threshold_attempts': '0',
            'requests-time_between_check-days': '0',
            'requests-time_between_check-hours': '0',
            'requests-time_between_check-minutes': '5',
            'requests-time_between_check-seconds': '0',
            'requests-time_between_check-weeks': '0',
            'requests-jitter_seconds': '0',
            'requests-workers': '10',
            'requests-timeout': '60',
        },
        follow_redirects=True,
    )
    assert res.status_code == 200, \
        f"Settings save crashed on blank LLM IntegerField submission (got {res.status_code})"
    # Sanity: the form must have actually validated and reached the LLM save path
    # — without this the test would trivially pass because the buggy code never ran.
    assert b'Settings updated.' in res.data, \
        "Settings form did not validate — the bug-path was never exercised. Check fixture fields."
    body = res.data.decode('utf-8', errors='replace')
    assert 'ValidationError' not in body, \
        "Pydantic ValidationError leaked into the response — blank IntegerField wasn't filtered"

    llm = ds.data['settings']['application'].get('llm') or {}
    assert llm.get('token_budget_month') == 50000, \
        f"Blank submission must preserve stored token_budget_month (got {llm.get('token_budget_month')!r})"
    assert llm.get('max_input_chars') == 200000, \
        f"Blank submission must preserve stored max_input_chars (got {llm.get('max_input_chars')!r})"
    assert llm.get('max_tokens_per_count_period') == 1000, \
        f"Blank submission must preserve stored max_tokens_per_count_period (got {llm.get('max_tokens_per_count_period')!r})"
    assert llm.get('local_token_multiplier') == 3, \
        f"Blank submission must preserve stored local_token_multiplier (got {llm.get('local_token_multiplier')!r})"

    delete_all_watches(client)


