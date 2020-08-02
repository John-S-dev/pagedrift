import shutil

from changedetectionio.strtobool import strtobool

from changedetectionio.validate_url import is_safe_valid_url

from flask import (
    flash,
    has_request_context
)
from flask_babel import gettext

