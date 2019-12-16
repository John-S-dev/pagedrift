#!/usr/bin/env python3

"""
Notification Service Module
Extracted from update_worker.py to provide standalone notification functionality
for both sync and async workers
"""
import datetime

import pytz
from loguru import logger
import time

from changedetectionio.notification import default_notification_format, valid_notification_formats


def _check_cascading_vars(datastore, var_name, watch):
    """
    Check notification variables in cascading priority:
    Individual watch settings > Tag settings > Global settings
    """
    from changedetectionio.notification import (
        USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH,
        default_notification_body,
        default_notification_title
    )

    # Would be better if this was some kind of Object where Watch can reference the parent datastore etc
    v = watch.get(var_name)
    if v and not watch.get('notification_muted'):
        if var_name == 'notification_format' and v == USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH:
            return datastore.data['settings']['application'].get('notification_format') or default_notification_format

        return v

    tags = datastore.get_all_tags_for_watch(uuid=watch.get('uuid'))
    if tags:
        for tag_uuid, tag in tags.items():
            v = tag.get(var_name)
            if v and not tag.get('notification_muted'):
                return v

    if datastore.data['settings']['application'].get(var_name):
        return datastore.data['settings']['application'].get(var_name)

    # Otherwise could be defaults
    if var_name == 'notification_format':
        return USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH
    if var_name == 'notification_body':
        return default_notification_body
    if var_name == 'notification_title':
        return default_notification_title

    return None


def watch_will_send_content_changed_notification(datastore, watch):
    """Single source of truth for: will a *content changed* notification actually be
    delivered for this watch?

    This mirrors exactly the decision the worker + send_content_changed_notification()
    make together: the watch must not be muted, and a notification URL must resolve via
    the watch > tag > global cascade. Anything that wants to know "is a notification
    going to fire?" (e.g. the worker deciding whether to spend tokens pre-computing the
    LLM change summary that fills the notification body) should ask here, so the answer
    can never drift from what actually gets sent.
    """
    if not watch or watch.get('notification_muted'):
        return False
    return bool(_check_cascading_vars(datastore, 'notification_urls', watch))


class FormattableTimestamp(str):
    """
    A str subclass representing a formatted datetime. As a plain string it renders
    with the default format, but can also be called with a custom format argument
    in Jinja2 templates:

        {{ change_datetime }}                        → '2024-01-15 10:30:00 UTC'
        {{ change_datetime(format='%Y') }}           → '2024'
        {{ change_datetime(format='%A') }}           → 'Monday'
        {{ change_datetime(format='%Y-%m-%d') }}     → '2024-01-15'

    Being a str subclass means it is natively JSON serializable.
    """
    _DEFAULT_FORMAT = '%Y-%m-%d %H:%M:%S %Z'

    def __new__(cls, timestamp):
        dt = datetime.datetime.fromtimestamp(int(timestamp), tz=pytz.UTC)
        local_tz = datetime.datetime.now().astimezone().tzinfo
        dt_local = dt.astimezone(local_tz)
        try:
            formatted = dt_local.strftime(cls._DEFAULT_FORMAT)
        except Exception:
            formatted = dt_local.isoformat()
        instance = super().__new__(cls, formatted)
        instance._dt = dt_local
        return instance

    def __call__(self, format=_DEFAULT_FORMAT):
        try:
            return self._dt.strftime(format)
        except Exception:
            return self._dt.isoformat()


class FormattableExtract(str):
    """
    A str subclass that holds only the extracted changed fragments from a diff.
    Used for {{diff_changed_from}} and {{diff_changed_to}} tokens.

        {{ diff_changed_from }}   → old value(s) only, e.g. "$99.99"
        {{ diff_changed_to }}     → new value(s) only, e.g. "$109.99"

    Multiple changed fragments are joined with newlines.
    Being a str subclass means it is natively JSON serializable.
    """
    def __new__(cls, prev_snapshot, current_snapshot, extract_fn, escape_output=False):
        if prev_snapshot or current_snapshot:
            from changedetectionio import diff as diff_module
            # word_diff=True is required — placemarker extraction regexes only exist in word-diff output
            raw = diff_module.render_diff(prev_snapshot or '', current_snapshot or '', word_diff=True)
            extracted = extract_fn(raw)
        else:
            extracted = ''
        if escape_output and extracted:
            # Placemarkers (@removed_PLACEMARKER_OPEN etc) contain no HTML chars,
            # so html_escape leaves them intact — they still get swapped to <span>
            # tags later by apply_service_tweaks. See GHSA-q8xq-qg4x-wphg.
            from markupsafe import escape as html_escape
            extracted = str(html_escape(extracted))
        instance = super().__new__(cls, extracted)
        return instance


class FormattableDiff(str):
    """
    A str subclass representing a rendered diff. As a plain string it renders
    with the default options for that variant, but can be called with custom
    arguments in Jinja2 templates:

        {{ diff }}                                    → default diff output
        {{ diff(lines=5) }}                           → truncate to 5 lines
        {{ diff(added_only=true) }}                   → only show added lines
        {{ diff(removed_only=true) }}                 → only show removed lines
        {{ diff(context=3) }}                         → 3 lines of context around changes
        {{ diff(word_diff=false) }}                   → line-level diff instead of word-level
        {{ diff(lines=10, added_only=true) }}         → combine args
        {{ diff_added(lines=5) }}                     → works on any diff_* variant too

    Being a str subclass means it is natively JSON serializable.
    """
    def __new__(cls, prev_snapshot, current_snapshot, escape_output=False, **base_kwargs):
        if prev_snapshot or current_snapshot:
            from changedetectionio import diff as diff_module
            rendered = diff_module.render_diff(prev_snapshot, current_snapshot, **base_kwargs)
        else:
            rendered = ''
        if escape_output and rendered:
            # Placemarkers (@removed_PLACEMARKER_OPEN etc) contain no HTML chars,
            # so html_escape leaves them intact — they still get swapped to <span>
            # tags later by apply_service_tweaks. See GHSA-q8xq-qg4x-wphg.
            from markupsafe import escape as html_escape
            rendered = str(html_escape(rendered))
        instance = super().__new__(cls, rendered)
        instance._prev = prev_snapshot
        instance._current = current_snapshot
        instance._base_kwargs = base_kwargs
        instance._escape_output = escape_output
        return instance

    def __call__(self, lines=None, added_only=False, removed_only=False, context=0,
                 word_diff=None, case_insensitive=False, ignore_junk=False):
        from changedetectionio import diff as diff_module
        kwargs = dict(self._base_kwargs)

        if added_only:
            kwargs['include_removed'] = False
        if removed_only:
            kwargs['include_added'] = False
        if context:
            kwargs['context_lines'] = int(context)
        if word_diff is not None:
            kwargs['word_diff'] = bool(word_diff)
        if case_insensitive:
            kwargs['case_insensitive'] = True
        if ignore_junk:
            kwargs['ignore_junk'] = True

        result = diff_module.render_diff(self._prev or '', self._current or '', **kwargs)

        if lines is not None:
            result = '\n'.join(result.splitlines()[:int(lines)])

        if self._escape_output and result:
            from markupsafe import escape as html_escape
            result = str(html_escape(result))

        return result



def set_basic_notification_vars(current_snapshot, prev_snapshot, watch, triggered_text, timestamp_changed=None):

    n_object = {
        'current_snapshot': current_snapshot,
        'prev_snapshot': prev_snapshot,
        'screenshot': watch.get_screenshot() if watch and watch.get('notification_screenshot') else None,
        'change_datetime': FormattableTimestamp(timestamp_changed) if timestamp_changed else None,
        'triggered_text': triggered_text,
        'uuid': watch.get('uuid') if watch else None,
        'watch_url': watch.get('url') if watch else None,
        'watch_open_url': (watch.open_link_override or watch.get('url')) if watch else None,
        'watch_uuid': watch.get('uuid') if watch else None,
        'watch_mime_type': watch.get('content-type')
    }

    # The \n's in the content from the above will get converted to <br> etc depending on the notification format

    if watch:
        n_object.update(watch.extra_notification_token_values())

    return n_object

class NotificationService:
    """
    Standalone notification service that handles all notification functionality
    previously embedded in the update_worker class
    """
    
    def __init__(self, datastore, notification_q):
        self.datastore = datastore
        self.notification_q = notification_q
    
    def queue_notification_for_watch(self, n_object: NotificationContextData, watch, date_index_from=-2, date_index_to=-1):
        """
        Queue a notification for a watch with full diff rendering and template variables
        """
        from changedetectionio.notification import USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH

        if not isinstance(n_object, NotificationContextData):
            raise TypeError(f"Expected NotificationContextData, got {type(n_object)}")

        dates = []
        trigger_text = ''

        if watch:
            watch_history = watch.history
            dates = list(watch_history.keys())
            trigger_text = watch.get('trigger_text', [])

        # Add text that was triggered
        if len(dates):
            snapshot_contents = watch.get_history_snapshot(timestamp=dates[-1])
        else:
            snapshot_contents = "No snapshot/history available, the watch should fetch atleast once."

        # If we ended up here with "System default"
        if n_object.get('notification_format') == USE_SYSTEM_DEFAULT_NOTIFICATION_FORMAT_FOR_WATCH:
            n_object['notification_format'] = self.datastore.data['settings']['application'].get('notification_format')


        triggered_text = ''
        if len(trigger_text):
            from . import html_tools
            triggered_text = html_tools.get_triggered_text(content=snapshot_contents, trigger_text=trigger_text)
            if triggered_text:
                triggered_text = '\n'.join(triggered_text)

        # Could be called as a 'test notification' with only 1 snapshot available
        prev_snapshot = "Example text: example test\nExample text: change detection is cool\nExample text: some more examples\n"
        current_snapshot = "Example text: example test\nExample text: change detection is fantastic\nExample text: even more examples\nExample text: a lot more examples"

        if len(dates) > 1:
            prev_snapshot = watch.get_history_snapshot(timestamp=dates[date_index_from])
            current_snapshot = watch.get_history_snapshot(timestamp=dates[date_index_to])


        n_object.update(set_basic_notification_vars(current_snapshot=current_snapshot,
                                                    prev_snapshot=prev_snapshot,
                                                    watch=watch,
                                                    triggered_text=triggered_text,
                                                    timestamp_changed=dates[date_index_to]))

        if self.notification_q:
            logger.debug("Queued notification for sending")
            self.notification_q.put(n_object)
        else:
            logger.debug("Not queued, no queue defined. Just returning processed data")
            return n_object

    def send_content_changed_notification(self, watch_uuid):
        """
        Send notification when content changes are detected
        """
        n_object = NotificationContextData()
        watch = self.datastore.data['watching'].get(watch_uuid)
        if not watch:
            return

        watch_history = watch.history
        dates = list(watch_history.keys())
        # Theoretically it's possible that this could be just 1 long,
        # - In the case that the timestamp key was not unique
        if len(dates) == 1:
            raise ValueError(
                "History index had 2 or more, but only 1 date loaded, timestamps were not unique? maybe two of the same timestamps got written, needs more delay?"
            )

        # Should be a better parent getter in the model object

        # Prefer - Individual watch settings > Tag settings >  Global settings (in that order)
        # this change probably not needed?
        n_object['notification_urls'] = _check_cascading_vars(self.datastore, 'notification_urls', watch)
        n_object['notification_title'] = _check_cascading_vars(self.datastore,'notification_title', watch)
        n_object['notification_body'] = _check_cascading_vars(self.datastore,'notification_body', watch)
        n_object['notification_format'] = _check_cascading_vars(self.datastore,'notification_format', watch)

        # Attach LLM results so notification tokens render correctly
        n_object['_llm_result'] = watch.get('_llm_result')
        n_object['_llm_intent'] = watch.get('_llm_intent', '')
        n_object['_llm_change_summary'] = watch.get('_llm_change_summary', '')

        # (Individual watch) Only prepare to notify if the rules above matched
        queued = False
        if n_object and n_object.get('notification_urls'):
            queued = True

            count = watch.get('notification_alert_count', 0) + 1
            self.datastore.update_watch(uuid=watch_uuid, update_obj={'notification_alert_count': count})

            self.queue_notification_for_watch(n_object=n_object, watch=watch)

        return queued

    def send_filter_failure_notification(self, watch_uuid):
        """
        Send notification when CSS/XPath filters fail consecutively
        """
        threshold = self.datastore.data['settings']['application'].get('filter_failure_notification_threshold_attempts')
        watch = self.datastore.data['watching'].get(watch_uuid)
        if not watch:
            return

        filter_list = ", ".join(watch['include_filters'])
        # @todo - This could be a markdown template on the disk, apprise will convert the markdown to HTML+Plaintext parts in the email, and then 'markup_text_links_to_html_links' is not needed
        body = f"""Hello,

