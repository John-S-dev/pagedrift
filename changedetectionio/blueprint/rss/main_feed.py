from flask import make_response, request, url_for, redirect



        # @todo needs a .itemsWithTag() or something - then we can use that in Jinaj2 and throw this away
        for uuid, watch in datastore.data['watching'].items():
            # @todo tag notification_muted skip also (improve Watch model)
            if datastore.data['settings']['application'].get('rss_hide_muted_watches') and watch.get('notification_muted'):
                continue
            if limit_tag and not limit_tag in watch['tags']:
                continue
            sorted_watches.append(watch)

        sorted_watches.sort(key=lambda x: x.last_changed, reverse=False)

        fg = FeedGenerator()
        fg.title('changedetection.io')
        fg.description('Feed description')
        fg.link(href='https://changedetection.io')
        notification_service = NotificationService(datastore=datastore, notification_q=False)

        for watch in sorted_watches:

            dates = list(watch.history.keys())
            # Re #521 - Don't bother processing this one if theres less than 2 snapshots, means we never had a change detected.
            if len(dates) < 2:
                continue

            if not watch.viewed:
                # Re #239 - GUID needs to be individual for each event
                # @todo In the future make this a configurable link back (see work on BASE_URL https://github.com/dgtlmoon/changedetection.io/pull/228)
                watch_label = get_watch_label(datastore, watch)
                timestamp_to = dates[-1]
                timestamp_from = dates[-2]
                guid = generate_watch_guid(watch, timestamp_to)
                # Because we are called via whatever web server, flask should figure out the right path
                diff_link = {'href': url_for('ui.ui_diff.diff_history_page', uuid=watch['uuid'], _external=True)}

                # Get template and build notification context
                n_body_template = get_rss_template(datastore, watch, rss_content_format,
                                                   RSS_TEMPLATE_HTML_DEFAULT, RSS_TEMPLATE_PLAINTEXT_DEFAULT)

                n_object = build_notification_context(watch, timestamp_from, timestamp_to,
                                                     watch_label, n_body_template, rss_content_format)

                # Render notification
                res = render_notification(n_object, notification_service, watch, datastore)

                # Create and populate feed entry
                fe = fg.add_entry()
                populate_feed_entry(fe, watch, res['body'], guid, timestamp_to, link=diff_link)
                fe.title(title=watch_label)  # Override title to not include suffix
                add_watch_categories(fe, watch, datastore)

        response = make_response(fg.rss_str())
        response.headers.set('Content-Type', 'application/rss+xml;charset=utf-8')
        logger.trace(f"RSS generated in {time.time() - now:.3f}s")
        return response
