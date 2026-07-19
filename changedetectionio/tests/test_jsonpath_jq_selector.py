#!/usr/bin/env python3
# coding=utf-8

import time
from flask import url_for
from markupsafe import escape
from . util import live_server_setup, wait_for_all_checks, delete_all_watches
import pytest
import os
jq_support = True

try:
    import jq
except ModuleNotFoundError:
    jq_support = False



def test_jsonp_treated_as_plaintext():
    from ..processors.magic import guess_stream_type

    # JSONP content (server wrongly claims application/json) should be detected as plaintext
    # Callback names are arbitrary identifiers, not always 'cb'
    jsonp_content = 'jQuery123456({ "version": "8.0.41", "url": "https://example.com/app.apk" })'
    result = guess_stream_type(http_content_header="application/json", content=jsonp_content)
    assert result.is_json is False
    assert result.is_plaintext is True

    # Variation with dotted callback name e.g. jQuery.cb(...)
    jsonp_dotted = 'some.callback({ "version": "1.0" })'
    result = guess_stream_type(http_content_header="application/json", content=jsonp_dotted)
    assert result.is_json is False
    assert result.is_plaintext is True

    # Real JSON should still be detected as JSON
    json_content = '{ "version": "8.0.41", "url": "https://example.com/app.apk" }'
    result = guess_stream_type(http_content_header="application/json", content=json_content)
    assert result.is_json is True
    assert result.is_plaintext is False


def test_lone_surrogate_escapes_do_not_break_filters():
    """A \\uD800-style escape in the watched JSON must not take the whole document down.

    jq re-serializes the document for its own C parser, which rejects a lone high surrogate,
    so every jq:/jqraw: filter on the page used to error even when pointing at an unrelated
    field. On the json: path the surrogate instead reached the caller intact and blew up later
    in checksums and history writes. Valid pairs must keep working untouched.
    See: https://github.com/dgtlmoon/changedetection.io/issues/4273
    """
    from .. import html_tools

    BS = chr(92)  # build the escapes at runtime so no quoting layer eats them
    lone_high = '{"title": "Example ' + BS + 'uD800", "other": "untouched"}'
    lone_low = '{"title": "Example ' + BS + 'uDC00", "other": "untouched"}'
    valid_pair = '{"title": "smile ' + BS + 'uD83D' + BS + 'uDE00", "other": "untouched"}'

    filters = ["json:$.%s", "jq:.%s", "jqraw:.%s"] if jq_support else ["json:$.%s"]

    for content in (lone_high, lone_low):
        for f in filters:
            # An unrelated field must still be reachable
            text = html_tools.extract_json_as_string(content, f % "other")
            assert "untouched" in text

            # And the offending field itself resolves, with the surrogate replaced
            text = html_tools.extract_json_as_string(content, f % "title")
            assert "Example" in text
            assert not any(0xD800 <= ord(c) <= 0xDFFF for c in text)
            # Whatever comes back has to survive the downstream checksum/history write
            text.encode('utf-8')

    # A well-formed surrogate pair is a normal emoji and must be preserved as-is
    for f in filters:
        text = html_tools.extract_json_as_string(valid_pair, f % "title")
        assert '\U0001F600' in text
        text.encode('utf-8')

    # The surrogate can just as easily land in an object *key*, which has to be sanitized too -
    # otherwise the whole-document re-serialization still trips over it
    lone_key = '{"ti' + BS + 'uD800tle": "value", "other": "untouched"}'
    for f in ("json:$.other", "jq:.other", "jqraw:.other") if jq_support else ("json:$.other",):
        text = html_tools.extract_json_as_string(lone_key, f)
        assert "untouched" in text
        text.encode('utf-8')

    # Dumping the whole document exercises the key path directly
    for f in ("json:$", "jq:.") if jq_support else ("json:$",):
        text = html_tools.extract_json_as_string(lone_key, f)
        assert "value" in text
        assert not any(0xD800 <= ord(c) <= 0xDFFF for c in text)
        text.encode('utf-8')

    # Nested arrays and non-string scalars have to be walked too. The scalars come first
    # deliberately: detection short-circuits on the first surrogate it finds, so anything after
    # the offending value would never be visited.
    nested = ('{"count": 3, "flag": null, "ok": true, '
              '"items": ["clean", "bad' + BS + 'uD800", [1, "deep' + BS + 'uDC00"]]}')
    for f in ("json:$", "jq:.") if jq_support else ("json:$",):
        text = html_tools.extract_json_as_string(nested, f)
        assert "clean" in text and "deep" in text
        assert not any(0xD800 <= ord(c) <= 0xDFFF for c in text)
        text.encode('utf-8')

    # ...and the scalars must survive the round-trip unmangled
    assert html_tools.extract_json_as_string(nested, "json:$.count").strip() == "3"


def test_unittest_inline_extract_body():
    content = """
    <html>
        <head></head>
        <body>
            <pre style="word-wrap: break-word; white-space: pre-wrap;">
                {"testKey": 42}
            </pre>
        </body>
    </html>
    """
    from .. import html_tools

    # See that we can find the second <script> one, which is not broken, and matches our filter
    text = html_tools.extract_json_as_string(content, "json:$.testKey")
    assert text == '42'

def set_original_ext_response(datastore_path):
    data = """
        [
        {
            "isPriceLowered": false,
            "status": "ForSale",
            "statusOrig": "for sale"
        },
        {
            "_id": "5e7b3e1fb3262d306323ff1e",
            "listingsType": "consumer",
            "status": "ForSale",
            "statusOrig": "for sale"
        }
    ]
        """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(data)
    return None

def set_modified_ext_response(datastore_path):
    # This should get reformatted
    data = """ [ { "isPriceLowered": false,  "status": "Sold",  "statusOrig": "sold" }, {
        "_id": "5e7b3e1fb3262d306323ff1e",
        "listingsType": "consumer",
        "isPriceLowered": false,
        "status": "Sold"
    }
]
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(data)
    return None

def set_original_response(datastore_path):
    test_return_data = """
    {
      "employees": [
        {
          "id": 1,
          "name": "Pankaj",
          "salary": "10000"
        },
        {
          "name": "David",
          "salary": "5000",
          "id": 2
        }
      ],
      "boss": {
        "name": "Fat guy"
      },
      "available": true
    }
    """
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None


def set_json_response_with_html(datastore_path):
    test_return_data = """
    {
      "test": [
        {
          "html": "<b>"
        }
      ]
    }
    """
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None

