import os
import time
import re
from random import randint
from loguru import logger

from changedetectionio.content_fetchers import SCREENSHOT_MAX_HEIGHT_DEFAULT
from changedetectionio.content_fetchers.base import get_playwright_bypass_csp, manage_user_agent
from changedetectionio.jinja2_custom import render as jinja_render
from changedetectionio.validate_url import validate_fetch_url_async

def browser_steps_get_valid_steps(browser_steps: list):
    if browser_steps is not None and len(browser_steps):
        valid_steps = list(filter(
            lambda s: (s['operation'] and len(s['operation']) and s['operation'] != 'Choose one'),browser_steps))

        # Just incase they selected Goto site by accident with older JS
        if valid_steps and valid_steps[0]['operation'] == 'Goto site':
            del(valid_steps[0])

        return valid_steps
    return []


