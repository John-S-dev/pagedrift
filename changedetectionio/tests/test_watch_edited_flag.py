#!/usr/bin/env python3
"""
Test the watch edited flag functionality.

This tests the private __watch_was_edited flag that tracks when writable
watch fields are modified, which prevents skipping reprocessing when the
watch configuration has changed.
"""

import os
import time
from flask import url_for
from .util import live_server_setup, wait_for_all_checks


def set_test_content(datastore_path):
    """Write test HTML content to endpoint-content.txt for test server."""
    test_html = """<html>
     <body>
     <p>Test content for watch edited flag tests</p>
     <p>This content stays the same across checks</p>
     </body>
     </html>
    """
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_html)


