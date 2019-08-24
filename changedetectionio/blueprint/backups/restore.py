import io
import json
import os
import re
import shutil
import tempfile
import threading
import zipfile

from flask import Blueprint, render_template, flash, url_for, redirect, request
from flask_babel import gettext, lazy_gettext as _l
from wtforms import Form, BooleanField, SubmitField
from flask_wtf.file import FileField, FileAllowed
from loguru import logger

from changedetectionio.flask_app import login_optionally_required

# Maximum size of the uploaded zip file. Override via env var MAX_RESTORE_UPLOAD_MB.
_MAX_UPLOAD_BYTES = int(os.getenv("MAX_RESTORE_UPLOAD_MB", 256)) * 1024 * 1024
# Maximum total uncompressed size of all entries (zip-bomb guard). Override via MAX_RESTORE_DECOMPRESSED_MB.
_MAX_DECOMPRESSED_BYTES = int(os.getenv("MAX_RESTORE_DECOMPRESSED_MB", 1024)) * 1024 * 1024
# Only top-level directories whose name is a valid UUID are treated as watch/tag entries.
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


class RestoreForm(Form):
    zip_file = FileField(_l('Backup zip file'), validators=[
        FileAllowed(['zip'], _l('Must be a .zip backup file!'))
    ])
    include_groups = BooleanField(_l('Include groups'), default=True)
    include_groups_replace_existing = BooleanField(_l('Replace existing groups of the same UUID'), default=True)
    include_watches = BooleanField(_l('Include watches'), default=True)
    include_watches_replace_existing = BooleanField(_l('Replace existing watches of the same UUID'), default=True)
    submit = SubmitField(_l('Restore backup'))


