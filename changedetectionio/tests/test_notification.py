import json
import os
import time
import re
from flask import url_for
from loguru import logger

from .util import set_original_response, set_modified_response, set_more_modified_response, live_server_setup, wait_for_all_checks, wait_for_notification_endpoint_output
from . util import  extract_UUID_from_client
import logging
import base64

from changedetectionio.notification import (
    default_notification_body,
    default_notification_format,
    default_notification_title, valid_notification_formats
)
from ..diff import HTML_CHANGED_STYLE
from ..model import USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH
from ..notification_service import FormattableTimestamp


