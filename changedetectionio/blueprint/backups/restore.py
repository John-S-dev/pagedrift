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

class RestoreForm(Form):
    zip_file = FileField(_l('Backup zip file'), validators=[
        FileAllowed(['zip'], _l('Must be a .zip backup file!'))
    ])
    include_groups = BooleanField(_l('Include groups'), default=True)
    include_groups_replace_existing = BooleanField(_l('Replace existing groups of the same UUID'), default=True)
    include_watches = BooleanField(_l('Include watches'), default=True)
    include_watches_replace_existing = BooleanField(_l('Replace existing watches of the same UUID'), default=True)
    submit = SubmitField(_l('Restore backup'))


