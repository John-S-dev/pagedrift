#!/usr/bin/env python3
"""
Security tests: LLM API key must never appear in any API response.

The LLM API key is a secret credential stored in
datastore.data['settings']['application']['llm']['api_key'].
It must never be leaked through any API endpoint — watch GET/list,
tag GET/list, system-info, notifications — even when the calling client
has a valid API token (which is a different kind of credential).

These tests set a recognisable fake key and then exhaustively check every
API endpoint's response body for the key string.
"""

import json

from flask import url_for

from changedetectionio.tests.util import live_server_setup, delete_all_watches

CANARY_KEY = 'sk-CANARY-SECRET-DO-NOT-EXPOSE-12345'


def _configure_llm(datastore, api_key=CANARY_KEY):
    """Inject a recognisable API key into the datastore LLM settings."""
    app = datastore.data['settings']['application']
    if 'llm' not in app:
        app['llm'] = {}
    app['llm'].update({
        'model': 'gpt-4o-mini',
        'api_key': api_key,
    })


def _api_token(client):
    return client.application.config.get('DATASTORE').data['settings']['application'].get('api_access_token')


def _key_in_response(response, key=CANARY_KEY) -> bool:
    """Return True if the canary key appears anywhere in the response body."""
    body = response.data.decode('utf-8', errors='replace')
    return key in body


# ---------------------------------------------------------------------------
# Watch endpoints
# ---------------------------------------------------------------------------

def test_watch_get_does_not_expose_llm_api_key(
        client, live_server, measure_memory_usage, datastore_path):
    """GET /api/v1/watch/<uuid> must not contain the LLM API key."""
    ds = client.application.config.get('DATASTORE')
    _configure_llm(ds)
    api_token = _api_token(client)

    test_url = url_for('test_endpoint', _external=True)
    res = client.post(
        '/api/v1/watch',
        data=json.dumps({'url': test_url}),
        headers={'content-type': 'application/json', 'x-api-key': api_token},
        follow_redirects=True,
    )
    assert res.status_code == 201
    uuid = res.json.get('uuid')

    res = client.get(
        f'/api/v1/watch/{uuid}',
        headers={'x-api-key': api_token},
    )
    assert res.status_code == 200
    assert not _key_in_response(res), \
        "LLM API key leaked in GET /api/v1/watch/<uuid> response"

    delete_all_watches(client)


def test_watch_list_does_not_expose_llm_api_key(
        client, live_server, measure_memory_usage, datastore_path):
    """GET /api/v1/watches must not contain the LLM API key."""
    ds = client.application.config.get('DATASTORE')
    _configure_llm(ds)
    api_token = _api_token(client)

    test_url = url_for('test_endpoint', _external=True)
    client.post(
        '/api/v1/watch',
        data=json.dumps({'url': test_url}),
        headers={'content-type': 'application/json', 'x-api-key': api_token},
        follow_redirects=True,
    )

    res = client.get('/api/v1/watch', headers={'x-api-key': api_token})
    assert res.status_code == 200
    assert not _key_in_response(res), \
        "LLM API key leaked in GET /api/v1/watch (list) response"

    delete_all_watches(client)


def test_watch_put_response_does_not_expose_llm_api_key(
        client, live_server, measure_memory_usage, datastore_path):
    """PUT /api/v1/watch/<uuid> response must not echo back the LLM API key."""
    ds = client.application.config.get('DATASTORE')
    _configure_llm(ds)
    api_token = _api_token(client)

    test_url = url_for('test_endpoint', _external=True)
    res = client.post(
        '/api/v1/watch',
        data=json.dumps({'url': test_url}),
        headers={'content-type': 'application/json', 'x-api-key': api_token},
        follow_redirects=True,
    )
    assert res.status_code == 201
    uuid = res.json.get('uuid')

    res = client.put(
        f'/api/v1/watch/{uuid}',
        headers={'x-api-key': api_token, 'content-type': 'application/json'},
        data=json.dumps({'url': test_url, 'title': 'updated'}),
    )
    assert res.status_code == 200
    assert not _key_in_response(res), \
        "LLM API key leaked in PUT /api/v1/watch/<uuid> response"

    delete_all_watches(client)


# ---------------------------------------------------------------------------
# Tag endpoints
# ---------------------------------------------------------------------------

def test_tag_get_does_not_expose_llm_api_key(
        client, live_server, measure_memory_usage, datastore_path):
    """GET /api/v1/tag/<uuid> must not contain the LLM API key."""
    ds = client.application.config.get('DATASTORE')
    _configure_llm(ds)
    api_token = _api_token(client)

    tag_uuid = ds.add_tag('security-test-tag')

    res = client.get(
        f'/api/v1/tag/{tag_uuid}',
        headers={'x-api-key': api_token},
    )
    assert res.status_code == 200
    assert not _key_in_response(res), \
        "LLM API key leaked in GET /api/v1/tag/<uuid> response"

    delete_all_watches(client)


def test_tag_list_does_not_expose_llm_api_key(
        client, live_server, measure_memory_usage, datastore_path):
    """GET /api/v1/tags must not contain the LLM API key."""
    ds = client.application.config.get('DATASTORE')
    _configure_llm(ds)
    api_token = _api_token(client)

    res = client.get('/api/v1/tags', headers={'x-api-key': api_token})
    assert res.status_code == 200
    assert not _key_in_response(res), \
        "LLM API key leaked in GET /api/v1/tags response"

    delete_all_watches(client)


def test_settings_form_preserves_api_key_when_submitted_blank(
        client, live_server, measure_memory_usage, datastore_path):
    """
    When the settings form is saved with an empty llm_api_key (which happens
    every time because PasswordField never pre-populates), the existing key
    must be preserved rather than cleared.
    """
    ds = client.application.config.get('DATASTORE')
    _configure_llm(ds, api_key='sk-should-be-kept')

    res = client.post(
        url_for('settings.settings_page'),
        data={
            'llm-model': 'gpt-4o',
            'llm-api_key': '',           # blank — PasswordField behaviour
            'llm-api_base': '',
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
    assert res.status_code == 200

    saved_key = ds.data['settings']['application'].get('llm', {}).get('api_key', '')
    assert saved_key == 'sk-should-be-kept', \
        f"Blank PasswordField submission must not clear the existing API key (got '{saved_key}')"

    delete_all_watches(client)


# ---------------------------------------------------------------------------
# SSRF — api_base must reject private/loopback/reserved hosts (GHSA-jrxm-qjfh-g54f)
# ---------------------------------------------------------------------------

# Hosts that is_private_hostname() must classify as restricted.
# 169.254.169.254 is the cloud metadata service (AWS/GCP IMDSv1).
_SSRF_PRIVATE_HOSTS = [
    'http://127.0.0.1:6379',
    'http://localhost:11434',
    'http://10.0.0.5:8080',
    'http://192.168.1.1',
    'http://169.254.169.254',
]


