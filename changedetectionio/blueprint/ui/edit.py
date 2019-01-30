from copy import deepcopy
import os
import importlib.resources
from flask import Blueprint, request, redirect, url_for, flash, render_template, abort
from flask_babel import gettext
from loguru import logger
from jinja2 import Environment, FileSystemLoader

        # AI on/off is not a "fill in the blank" field: a group that has taken the decision
        # (On or Off, i.e. not "leave it to each watch") decides for every watch in it (#4204),
        # so report it and let the template show the watch's own checkbox as overridden.
        for tag_uuid, tag in _watch_tags(watch):
            if tag_llm_decision(tag) is not None:
                result['llm_backend_profile'] = {
                    'value': tag_llm_decision(tag),
                    'group_name': tag.get('title', 'tag'),
                    'group_uuid': tag_uuid,
                }
                break

        for field in ('llm_intent', 'llm_change_summary'):
            if (watch.get(field) or '').strip():
                continue  # watch has its own value — editable, no group override
            for tag_uuid, tag in _watch_tags(watch):
                if not tag_llm_applies_to_watches(tag):
                    continue
                if (tag.get(field) or '').strip():
                    result[field] = {
                        'value': tag.get(field).strip(),
                        'group_name': tag.get('title', 'tag'),
                        'group_uuid': tag_uuid,
                    }
                    break
        return result

    def _watch_has_tag_options_set(watch):
        """This should be fixed better so that Tag is some proper Model, a tag is just a Watch also"""
        for tag_uuid, tag in datastore.data['settings']['application'].get('tags', {}).items():
            if tag_uuid in watch.get('tags', []) and (tag.get('include_filters') or tag.get('subtractive_selectors')):
                return True

    @edit_blueprint.route("/edit/<uuid_str:uuid>", methods=['GET', 'POST'])
    @login_optionally_required
    # https://stackoverflow.com/questions/42984453/wtforms-populate-form-with-data-if-data-exists
    # https://wtforms.readthedocs.io/en/3.0.x/forms/#wtforms.form.Form.populate_obj ?
    def edit_page(uuid):
        from changedetectionio import forms
        from changedetectionio.browser_steps.browser_steps import browser_step_ui_config
        from changedetectionio import processors
        import importlib

        if uuid == 'first':
            uuid = list(datastore.data['watching'].keys()).pop()
        # More for testing, possible to return the first/only
        if not datastore.data['watching'].keys():
            flash(gettext("No watches to edit"), "error")
            return redirect(url_for('watchlist.index'))

        if not uuid in datastore.data['watching']:
            flash(gettext("No watch with the UUID {} found.").format(uuid), "error")
            return redirect(url_for('watchlist.index'))

        switch_processor = request.args.get('switch_processor')
        if switch_processor:
            for p in processors.available_processors():
                if p[0] == switch_processor:
                    datastore.data['watching'][uuid]['processor'] = switch_processor
                    flash(gettext("Switched to mode - {}.").format(p[1]))
                    datastore.clear_watch_history(uuid)
                    redirect(url_for('ui_edit.edit_page', uuid=uuid))

        # be sure we update with a copy instead of accidently editing the live object by reference
        default = None
        while not default:
            try:
                default = deepcopy(datastore.data['watching'][uuid])
            except RuntimeError as e:
                # Dictionary changed
                continue

