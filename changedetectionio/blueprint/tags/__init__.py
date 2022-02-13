import threading
from flask import Blueprint, request, render_template, flash, url_for, redirect
from flask_babel import gettext
from loguru import logger

from changedetectionio.blueprint.tags.colour import safe_css_colour
from changedetectionio.store import ChangeDetectionStore
from changedetectionio.flask_app import login_optionally_required
from changedetectionio.llm.evaluator import get_llm_config as _get_llm_config


def construct_blueprint(datastore: ChangeDetectionStore):
    tags_blueprint = Blueprint('tags', __name__, template_folder="templates")

    # Used by any template that writes a tag colour into a <style> block
    tags_blueprint.add_app_template_filter(safe_css_colour, 'safe_css_colour')

    @tags_blueprint.route("/list", methods=['GET'])
    @login_optionally_required
    def tags_overview_page():
        from .form import SingleTag
        add_form = SingleTag(request.form)

        sorted_tags = sorted(datastore.data['settings']['application'].get('tags').items(), key=lambda x: x[1]['title'])

        from collections import Counter

        tag_count = Counter(tag for watch in datastore.data['watching'].values() if watch.get('tags') for tag in watch['tags'])

        from changedetectionio import processors
        output = render_template("groups-overview.html",
                                 app_rss_token=datastore.data['settings']['application'].get('rss_access_token'),
                                 available_tags=sorted_tags,
                                 form=add_form,
                                 generate_tag_colors=processors.generate_processor_badge_colors,
                                 tag_count=tag_count,
                                 wcag_text_color=processors.wcag_text_color,
                                 )

        return output

    @tags_blueprint.route("/add", methods=['POST'])
    @login_optionally_required
    def form_tag_add():
        from .form import SingleTag
        add_form = SingleTag(request.form)

        if not add_form.validate():
            for widget, l in add_form.errors.items():
                flash(','.join(l), 'error')
            return redirect(url_for('tags.tags_overview_page'))

        title = request.form.get('name').strip()

        if datastore.tag_exists_by_name(title):
            flash(gettext('The tag "{}" already exists').format(title), "error")
            return redirect(url_for('tags.tags_overview_page'))

        datastore.add_tag(title)
        flash(gettext("Tag added"))


        return redirect(url_for('tags.tags_overview_page'))

    @tags_blueprint.route("/mute/<uuid_str:uuid>", methods=['POST'])
    @login_optionally_required
    def mute(uuid):
        tag = datastore.data['settings']['application']['tags'].get(uuid)
        if tag:
            tag['notification_muted'] = not tag['notification_muted']
            tag.commit()
        return redirect(url_for('tags.tags_overview_page'))

    @tags_blueprint.route("/delete/<uuid_str:uuid>", methods=['POST'])
    @login_optionally_required
    def delete(uuid):
        # Delete the tag from settings immediately
        if datastore.data['settings']['application']['tags'].get(uuid):
            del datastore.data['settings']['application']['tags'][uuid]

        # Remove tag from all watches in background thread to avoid blocking
        def remove_tag_background(tag_uuid):
            """Background thread to remove tag from watches - discarded after completion."""
            removed_count = 0
            try:
                for watch_uuid, watch in datastore.data['watching'].items():
                    if watch.get('tags') and tag_uuid in watch['tags']:
                        watch['tags'].remove(tag_uuid)
                        watch.commit()
                        removed_count += 1
                logger.info(f"Background: Tag {tag_uuid} removed from {removed_count} watches")
            except Exception as e:
                logger.error(f"Error removing tag from watches: {e}")

        # Start daemon thread
        threading.Thread(target=remove_tag_background, args=(uuid,), daemon=True).start()

        flash(gettext("Tag deleted, removing from watches in background"))
        return redirect(url_for('tags.tags_overview_page'))

    @tags_blueprint.route("/unlink/<uuid_str:uuid>", methods=['POST'])
    @login_optionally_required
    def unlink(uuid):
        # Unlink tag from all watches in background thread to avoid blocking
        def unlink_tag_background(tag_uuid):
            """Background thread to unlink tag from watches - discarded after completion."""
            unlinked_count = 0
            try:
                for watch_uuid, watch in datastore.data['watching'].items():
                    if watch.get('tags') and tag_uuid in watch['tags']:
                        watch['tags'].remove(tag_uuid)
                        watch.commit()
                        unlinked_count += 1
                logger.info(f"Background: Tag {tag_uuid} unlinked from {unlinked_count} watches")
            except Exception as e:
                logger.error(f"Error unlinking tag from watches: {e}")

        # Start daemon thread
        threading.Thread(target=unlink_tag_background, args=(uuid,), daemon=True).start()

        flash(gettext("Unlinking tag from watches in background"))
        return redirect(url_for('tags.tags_overview_page'))

    @tags_blueprint.route("/delete_all", methods=['POST'])
    @login_optionally_required
    def delete_all():

        for tag_uuid in list(datastore.data['settings']['application']['tags'].keys()):
# TagsDict 'del' handler will remove the dir
            del datastore.data['settings']['application']['tags'][tag_uuid]


        # Clear tags from all watches in background thread to avoid blocking
        def clear_all_tags_background():
            """Background thread to clear tags from all watches - discarded after completion."""
            cleared_count = 0
            try:
                for watch_uuid, watch in datastore.data['watching'].items():
                    watch['tags'] = []
                    watch.commit()
                    cleared_count += 1
                logger.info(f"Background: Cleared tags from {cleared_count} watches")
            except Exception as e:
                logger.error(f"Error clearing tags from watches: {e}")

        # Start daemon thread
        threading.Thread(target=clear_all_tags_background, daemon=True).start()

        flash(gettext("All tags deleted, clearing from watches in background"))
        return redirect(url_for('tags.tags_overview_page'))

    @tags_blueprint.route("/edit/<uuid_str:uuid>", methods=['GET'])
    @login_optionally_required
    def form_tag_edit(uuid):
        from changedetectionio.blueprint.tags.form import group_restock_settings_form
        if uuid == 'first':
            uuid = list(datastore.data['settings']['application']['tags'].keys()).pop()

