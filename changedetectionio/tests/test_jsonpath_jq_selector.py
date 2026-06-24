#!/usr/bin/env python3
# coding=utf-8

import time
from flask import url_for
from markupsafe import escape
from . util import live_server_setup, wait_for_all_checks, delete_all_watches
import pytest
import os
jq_support = True

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

