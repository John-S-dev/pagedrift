import os
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones
import secrets
import time
import flask_login
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_babel import gettext

def construct_blueprint(datastore: ChangeDetectionStore):
    from changedetectionio.llm.evaluator import is_llm_features_disabled
    settings_blueprint = Blueprint('settings', __name__, template_folder="templates")
    if not is_llm_features_disabled():
        from changedetectionio.blueprint.settings.llm import construct_llm_blueprint
        settings_blueprint.register_blueprint(construct_llm_blueprint(datastore), url_prefix='/llm')

    # Notification settings live in their own child blueprint so future backends
    # (simple_email, webhooks, etc.) slot in as /settings/notifications/<backend>
    # without further URL-shaping churn.
    from changedetectionio.blueprint.settings.notifications import construct_notifications_blueprint
    settings_blueprint.register_blueprint(
        construct_notifications_blueprint(datastore), url_prefix='/notifications',
    )

    @settings_blueprint.route("", methods=['GET', "POST"])
    @login_optionally_required
    def settings_page():
        from changedetectionio import forms
        from changedetectionio.pluggy_interface import (
            get_plugin_settings_tabs,
            load_plugin_settings,
            save_plugin_settings
        )


        default = deepcopy(datastore.data['settings'])

