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

