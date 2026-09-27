#!/usr/bin/env python3

import sys
import os

from changedetectionio.model import USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from changedetectionio.widgets import TernaryNoneBooleanField
from wtforms import Form

