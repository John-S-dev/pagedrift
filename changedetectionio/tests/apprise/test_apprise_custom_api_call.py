import json
from unittest.mock import patch

import pytest
import requests
from apprise.utils.parse import parse_url as apprise_parse_url

from changedetectionio.notification.apprise_plugin.custom_handlers import (
    _get_auth,
    _get_headers,
    _get_params,
    apprise_http_custom_handler,
    SUPPORTED_HTTP_METHODS,
)


@pytest.mark.parametrize(
    "url,expected_auth",
    [
        ("get://user:pass@localhost:9999", ("user", "pass")),
        ("get://user@localhost:9999", "user"),
        ("get://localhost:9999", ""),
        ("get://user%20name:pass%20word@localhost:9999", ("user name", "pass word")),
    ],
)
def test_get_auth(url, expected_auth):
    """Test authentication extraction with various URL formats."""
    parsed_url = apprise_parse_url(url)
    assert _get_auth(parsed_url) == expected_auth


@pytest.mark.parametrize(
    "url,body,expected_content_type",
    [
        (
            "get://localhost:9999?+content-type=application/xml",
            "test",
            "application/xml",
        ),
        ("get://localhost:9999", '{"key": "value"}', "application/json; charset=utf-8"),
        ("get://localhost:9999", "plain text", None),
        ("get://localhost:9999?+content-type=text/plain", "test", "text/plain"),
    ],
)
def test_get_headers(url, body, expected_content_type):
    """Test header extraction and content type detection."""
    parsed_url = apprise_parse_url(url)
    headers = _get_headers(parsed_url, body)

    if expected_content_type:
        assert headers.get("Content-Type") == expected_content_type


