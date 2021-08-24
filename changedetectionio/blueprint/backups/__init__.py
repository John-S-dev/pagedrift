import datetime
import glob
import threading

from flask import Blueprint, render_template, send_from_directory, flash, url_for, redirect, abort
from flask_babel import gettext
import os

from changedetectionio.store import ChangeDetectionStore
from changedetectionio.flask_app import login_optionally_required
from loguru import logger

BACKUP_FILENAME_FORMAT = "changedetection-backup-{}.zip"


