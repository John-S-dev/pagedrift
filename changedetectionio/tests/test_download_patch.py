#!/usr/bin/env python3
"""
Tests for the /diff/<uuid>/download-patch endpoint.

The route should accept from_version and to_version query parameters,
read those two snapshots from the watch history, generate a unified diff
patch, and return it as a downloadable text/plain file.
"""

from flask import url_for

