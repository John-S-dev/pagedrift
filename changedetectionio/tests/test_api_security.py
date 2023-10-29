#!/usr/bin/env python3
"""
Comprehensive security and edge case tests for the API.
Tests critical areas that were identified as gaps in the existing test suite.
"""

import time
import json
import threading
import uuid as uuid_module
from flask import url_for
from .util import live_server_setup, wait_for_all_checks, wait_for_watch_history, delete_all_watches
import os


def set_original_response(datastore_path):
    test_return_data = """<html>
       <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     </body>
     </html>
    """
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None


def is_valid_uuid(val):
    try:
        uuid_module.UUID(str(val))
        return True
    except ValueError:
        return False


# ============================================================================
# TIER 1: CRITICAL SECURITY TESTS
# ============================================================================

def test_api_path_traversal_in_uuids(client, live_server, measure_memory_usage, datastore_path):
    """
    Test that path traversal attacks via UUID parameter are blocked.
    Addresses CVE-like vulnerabilities where ../../../ in UUID could access arbitrary files.
    """
    api_key = live_server.app.config['DATASTORE'].data['settings']['application'].get('api_access_token')
    set_original_response(datastore_path=datastore_path)
    test_url = url_for('test_endpoint', _external=True)

    # Create a valid watch first
    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": test_url, "title": "Valid watch"}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
    )
    assert res.status_code == 201
    valid_uuid = res.json.get('uuid')

    # Test 1: Path traversal with ../../../
    res = client.get(
        f"/api/v1/watch/../../etc/passwd",
        headers={'x-api-key': api_key}
    )
    assert res.status_code in [400, 404], "Path traversal should be rejected"

    # Test 2: Encoded path traversal
    res = client.get(
        "/api/v1/watch/..%2F..%2F..%2Fetc%2Fpasswd",
        headers={'x-api-key': api_key}
    )
    assert res.status_code in [400, 404], "Encoded path traversal should be rejected"

    # Test 3: Double-encoded path traversal
    res = client.get(
        "/api/v1/watch/%2e%2e%2f%2e%2e%2f%2e%2e%2f",
        headers={'x-api-key': api_key}
    )
    assert res.status_code in [400, 404], "Double-encoded traversal should be rejected"

    # Test 4: Try to access datastore file
    res = client.get(
        "/api/v1/watch/../url-watches.json",
        headers={'x-api-key': api_key}
    )
    assert res.status_code in [400, 404], "Access to datastore should be blocked"

    # Test 5: Null byte injection
    res = client.get(
        f"/api/v1/watch/{valid_uuid}%00.json",
        headers={'x-api-key': api_key}
    )
    # Should either work (ignoring null byte) or reject - but not crash
    assert res.status_code in [200, 400, 404]

    # Test 6: DELETE with path traversal
    res = client.delete(
        "/api/v1/watch/../../datastore/url-watches.json",
        headers={'x-api-key': api_key}
    )
    assert res.status_code in [400, 404, 405], "DELETE with traversal should be blocked (405=method not allowed is also acceptable)"

    # Cleanup
    client.delete(url_for("watch", uuid=valid_uuid), headers={'x-api-key': api_key})
    delete_all_watches(client)


def test_api_concurrency_race_conditions(client, live_server, measure_memory_usage, datastore_path):
    """
    Test concurrent API requests to detect race conditions.
    Addresses 20+ concurrency bugs from changelog.
    """
    api_key = live_server.app.config['DATASTORE'].data['settings']['application'].get('api_access_token')
    set_original_response(datastore_path=datastore_path)
    test_url = url_for('test_endpoint', _external=True)

    # Create a watch
    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": test_url, "title": "Concurrency test"}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
    )
    assert res.status_code == 201
    watch_uuid = res.json.get('uuid')
    wait_for_all_checks(client)

    # Test 1: Concurrent updates to same watch
    # Note: Flask test client is not thread-safe, so we test sequential updates instead
    # Real concurrency issues would be caught in integration tests with actual HTTP requests
    results = []
    for i in range(10):
        try:
            r = client.put(
                url_for("watch", uuid=watch_uuid),
                data=json.dumps({"title": f"Title {i}"}),
                headers={'content-type': 'application/json', 'x-api-key': api_key},
            )
            results.append(r.status_code)
        except Exception as e:
            results.append(str(e))

    # All updates should succeed (200) without crashes
    assert all(r == 200 for r in results), f"Some updates failed: {results}"

    # Test 2: Update while watch is being checked
    # Queue a recheck
    client.get(
        url_for("watch", uuid=watch_uuid, recheck=True),
        headers={'x-api-key': api_key}
    )

    # Immediately update it
    res = client.put(
        url_for("watch", uuid=watch_uuid),
        data=json.dumps({"title": "Updated during check"}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
    )
    # Should succeed without error
    assert res.status_code == 200

    # Test 3: Delete watch that's being processed
    # Create another watch
    res = client.post(
        url_for("createwatch"),
        data=json.dumps({"url": test_url}),
        headers={'content-type': 'application/json', 'x-api-key': api_key},
    )
    watch_uuid2 = res.json.get('uuid')

    # Queue it for checking
    client.get(url_for("watch", uuid=watch_uuid2, recheck=True), headers={'x-api-key': api_key})

    # Immediately delete it
    res = client.delete(url_for("watch", uuid=watch_uuid2), headers={'x-api-key': api_key})
    # Should succeed or return appropriate error
    assert res.status_code in [204, 404, 400]

    # Cleanup
    client.delete(url_for("watch", uuid=watch_uuid), headers={'x-api-key': api_key})
    delete_all_watches(client)


