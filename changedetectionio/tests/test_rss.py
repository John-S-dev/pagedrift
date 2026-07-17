#!/usr/bin/env python3
import email.utils
import os
import time
import pytest
from flask import url_for
from .util import set_original_response, set_modified_response, live_server_setup, wait_for_all_checks, extract_rss_token_from_UI, \
    extract_UUID_from_client, delete_all_watches
from loguru import logger
from ..blueprint.rss import RSS_FORMAT_TYPES


def set_html_content(datastore_path, content):
    test_return_data = f"""<html>
       <body>
     Some initial text<br>
     <p>{content}</p>
     <br>
     So let's see what happens.  <br>
     </body>
     </html>
    """

    # Write as UTF-8 encoded bytes
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "wb") as f:
        f.write(test_return_data.encode('utf-8'))


