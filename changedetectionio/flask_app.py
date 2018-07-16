#!/usr/bin/env python3

from changedetectionio import worker_pool
from changedetectionio.queue_handlers import NotificationQueue, RecheckPriorityQueue
from changedetectionio.strtobool import strtobool

# Create specific signals for application events
# Make this a global singleton to avoid multiple signal objects
watch_check_update = signal('watch_check_update', doc='Signal sent when a watch check is completed')
from flask_babel import Babel, get_locale, gettext
from flask_wtf import CSRFProtect
from loguru import logger

