"""
Utility functions for RSS feed generation.
"""

from changedetectionio.notification.handler import process_notification
from changedetectionio.notification_service import NotificationContextData, _check_cascading_vars
from loguru import logger
import datetime
import pytz
import re


BAD_CHARS_REGEX = r'[\x00-\x08\x0B\x0C\x0E-\x1F]'


