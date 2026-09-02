import os
import time

from flask import Blueprint, request, make_response, render_template, redirect, url_for, flash, session
from flask_paginate import Pagination, get_page_parameter
from flask_babel import gettext as _

from changedetectionio import forms
from changedetectionio import processors
from changedetectionio import worker_pool
from changedetectionio.store import ChangeDetectionStore
from changedetectionio.auth_decorator import login_optionally_required
# Shared filtering — the single source of truth, also used by the ui blueprint's
# bulk actions so a filtered view and the actions taken on it always agree.
from changedetectionio.blueprint.watchlist import filters as wl_filters
from changedetectionio.blueprint.watchlist.row_context import watch_row_context

def construct_blueprint(datastore: ChangeDetectionStore, update_q, queuedWatchMetaData):
    watchlist_blueprint = Blueprint('watchlist', __name__, template_folder="templates")

    @watchlist_blueprint.route("/toggle", methods=['POST'])
    @login_optionally_required
    def toggle():
        op = request.args.get('op')
        uuid = request.args.get('uuid')
        watch = datastore.data['watching'].get(uuid)

        if not watch:
            flash(_('Watch not found'), 'error')
        else:
            if op == 'pause':
                watch.toggle_pause()
            elif op == 'mute':
                watch.toggle_mute()
            watch.commit()

        return redirect(url_for('watchlist.index', tag=request.args.get('tag')))

    @watchlist_blueprint.route("/", methods=['GET'])
    @login_optionally_required
    def index():
        active_tag_req = request.args.get('tag', '').lower().strip()
        active_tag_uuid = active_tag = None

        # Be sure limit_tag is a uuid
        if active_tag_req:
            for uuid, tag in datastore.data['settings']['application'].get('tags', {}).items():
                if active_tag_req == tag.get('title', '').lower().strip() or active_tag_req == uuid:
                    active_tag = tag
                    active_tag_uuid = uuid
                    break

        # Redirect for the old rss path which used the /?rss=true
        if request.args.get('rss'):
            return redirect(url_for('rss.feed', tag=active_tag_uuid))

        # Sort by last_changed and add the uuid which is usually the key..
        sorted_watches = []
        active_processor = request.args.get('processor', '').strip()
        # Toolbar facet counts are tallied over the tag/processor/search context but
        # independently of the active status toggle, so the .seg numbers stay stable
        # as you switch between All / Unread / Deals / With errors.
        errored_count = 0
        deals_count = 0
        unread_count = 0
        processor_counts = {}
        list_filters = wl_filters.list_filters_from_args(datastore, request.args)
        for uuid, watch in datastore.data['watching'].items():
            # The processor facet is counted over the tag/search base (ignoring the
            # selected processor) so every detected processor shows up and you can
            # switch between them.
            if not wl_filters.watch_matches_tag(datastore, watch, list_filters):
                continue
            if not wl_filters.watch_passes_search(watch, list_filters):
                continue
            proc = watch.get('processor')
            if proc:
                processor_counts[proc] = processor_counts.get(proc, 0) + 1

            # Narrow to the selected processor for the remaining facets + the list.
            if list_filters['processor'] and proc != list_filters['processor']:
                continue
            if watch.get('last_error'):
                errored_count += 1
            if wl_filters.watch_is_deal(watch):
                deals_count += 1
            # Unread = changed and not yet viewed — same test the 'unread' status
            # filter uses, so this count matches what clicking Unread shows.
            if not (watch.viewed or watch.last_changed == 0):
                unread_count += 1
            if wl_filters.watch_passes_status(watch, list_filters):
                sorted_watches.append(watch)

        form = forms.quickWatchForm(request.form)
        page = request.args.get(get_page_parameter(), type=int, default=1)
        total_count = len(sorted_watches)

        pagination = Pagination(page=page,
                                total=total_count,
                                per_page=datastore.data['settings']['application'].get('pager_size', 50),
                                css_framework="semantic",
                                display_msg=_('displaying <b>{start} - {end}</b> {record_name} in total <b>{total}</b>'),
                                record_name=_('records'))

        sorted_tags = sorted(datastore.data['settings']['application'].get('tags').items(), key=lambda x: x[1]['title'])

