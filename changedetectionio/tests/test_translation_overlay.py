"""Guards for the translation overlay layer (changedetectionio/translations_overlay).

The overlay is a second gettext tree merged on top of ``changedetectionio/translations``, letting a
deployment reword individual strings without editing the ``_()`` call site. See that directory's
README.md. Three separate things can break it, so there is a test for each.

1. Overlay entries key on the exact upstream msgid. When a string is reworded upstream the override
   stops matching and silently reverts to upstream wording - no error, no log entry.
   ``test_overlay_catalogs_are_valid`` makes that a build failure.

2. The layering relies on Flask-Babel merging catalogs with ``dict.update`` semantics (later
   directory wins per-message). Were a Flask-Babel upgrade to change that to an ``add_fallback``
   chain, overrides would stop applying while everything still looked fine.
   ``test_overlay_overrides_a_string_in_a_rendered_page`` pins it against a real rendered page.

3. The directory has to actually reach ``BABEL_TRANSLATION_DIRECTORIES``.
   ``test_overlay_dir_*`` cover the wiring in flask_app.py, including the env var.
"""

import os
import subprocess
import sys

import pytest
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from flask import url_for

