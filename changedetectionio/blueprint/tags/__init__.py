import threading
from flask import Blueprint, request, render_template, flash, url_for, redirect
from flask_babel import gettext
from loguru import logger

from changedetectionio.blueprint.tags.colour import safe_css_colour
from changedetectionio.store import ChangeDetectionStore
from changedetectionio.flask_app import login_optionally_required
from changedetectionio.llm.evaluator import get_llm_config as _get_llm_config


