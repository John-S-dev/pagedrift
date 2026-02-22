from flask import Blueprint, request, redirect, url_for, flash, render_template, make_response, send_from_directory
from flask_babel import gettext

from changedetectionio.diff import (
    REMOVED_STYLE, ADDED_STYLE, REMOVED_INNER_STYLE, ADDED_INNER_STYLE,
    REMOVED_PLACEMARKER_OPEN, REMOVED_PLACEMARKER_CLOSED,
    ADDED_PLACEMARKER_OPEN, ADDED_PLACEMARKER_CLOSED,
    CHANGED_PLACEMARKER_OPEN, CHANGED_PLACEMARKER_CLOSED,
    CHANGED_INTO_PLACEMARKER_OPEN, CHANGED_INTO_PLACEMARKER_CLOSED
)
from changedetectionio.store import ChangeDetectionStore
from changedetectionio.blueprint import plaintext_response
from changedetectionio.auth_decorator import login_optionally_required


def construct_blueprint(datastore: ChangeDetectionStore):
    diff_blueprint = Blueprint('ui_diff', __name__, template_folder="../ui/templates")

    @diff_blueprint.app_template_filter('diff_unescape_difference_spans')
    def diff_unescape_difference_spans(content):
        """Emulate Jinja2's auto-escape, then selectively unescape our diff spans."""
        from markupsafe import escape

