#!/usr/bin/env python3

# run from dir above changedetectionio/ dir
# python3 -m unittest changedetectionio.tests.unit.test_processor_config_path_traversal

"""Regression tests for GHSA-mh42-m7cg-49fr - arbitrary file write via the watch `processor` field.

A watch's `processor` is enum-validated by the API, but /imports/import puts
request.values.get('processor') into the watch verbatim. save_processor_config() then uses that
value as a filename (f'{processor}.json') and update_extra_watch_config() did
os.path.join(data_dir, filename) + open(filepath, 'w') with no containment - so a value like
'../../../../tmp/pwned' escaped the watch directory and wrote an attacker-named JSON file
anywhere the app user could reach. get_extra_watch_config() had the same traversal on read.

Three layers are asserted here: path containment in base.py (the security boundary), the filename
sanity check in save_processor_config(), and add_watch() refusing to persist an unknown processor
at all - which also covers the share-link import path, where 'processor' arrives in JSON fetched
from a remote URL.
"""

import os
import tempfile
import unittest

