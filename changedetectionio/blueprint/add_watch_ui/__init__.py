from flask import Blueprint, render_template, request, jsonify, make_response, flash, redirect, url_for
from flask_babel import gettext
from loguru import logger

from changedetectionio import forms
from changedetectionio.auth_decorator import login_optionally_required
from . import browser_config
from changedetectionio.store import ChangeDetectionStore
from changedetectionio.validate_url import is_fetch_url_allowed


def construct_blueprint(datastore: ChangeDetectionStore):
    add_watch_ui_blueprint = Blueprint('add_watch_ui', __name__, template_folder="templates", static_folder="static")

    @add_watch_ui_blueprint.route("/", methods=['GET'])
    @login_optionally_required
    def add_watch_ui_index():
        from changedetectionio.llm.evaluator import get_llm_config as _get_llm_config
        from changedetectionio.llm.ui_strings import LLM_INTENT_WATCH_PLACEHOLDER

        # Same gate that hides the sidebar link (sidebar-nav.html): with no browser that can
        # render a preview there is nothing for the visual selector to work on, so bounce
        # direct navigation rather than serving a page whose only outcome is an error.
        if not browser_config.has_visual_browser(datastore):
            flash(gettext("Adding a watch with a browser needs an interactive browser "
                          "(screenshots + element data) - none is configured."), 'error')
            return redirect(url_for('watchlist.index'))

        form = forms.quickWatchForm(None)
        llm_configured = bool(_get_llm_config(datastore))

        # Start on the browser the live preview would actually use
        form.fetch_backend.data = browser_config.default_visual_browser(datastore)

        return render_template(
            "add-watch-ui.html",
            form=form,
            llm_configured=llm_configured,
            llm_intent_watch_placeholder=LLM_INTENT_WATCH_PLACEHOLDER,
            # Listed but not selectable (the system default when it can't render a preview)
            unusable_browsers=browser_config.unusable_values(datastore),
            system_default_browser=browser_config.system_default_description(datastore),
        )

    @add_watch_ui_blueprint.route("/snapshot", methods=['POST'])
    @login_optionally_required
    def add_watch_ui_snapshot():
        """One-shot live fetch of an arbitrary URL for the Add Watch visual selector.

        Reuses the same browser machinery as Browser Steps (browsersteps_live_ui +
        the dedicated async loop) but without needing a persisted watch - we just
        connect, "Goto site", grab the screenshot + xpath element data, then tear
        the browser down again. Element selection then happens client-side on the
        returned data, exactly like the watch Edit page's visual selector.

        POST-only and CSRF protected on purpose: this drives a real browser fetch and
        writes a temporary watch dir, so as a GET it could be triggered cross-origin
        (or by any tag/link that issues a GET) without the operator's consent.
        """
        import base64
        from changedetectionio.blueprint.browser_steps import (
            run_async_in_browser_loop,
            _close_session_resources,
            acquire_browser_for_fetcher,
        )
        from changedetectionio.browser_steps.browser_steps import browsersteps_live_ui

        # Opportunistically sweep snapshots that were fetched but never saved.
        datastore.cleanup_temporary_watches()

