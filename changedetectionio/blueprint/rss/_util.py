"""
Utility functions for RSS feed generation.
"""

from changedetectionio.notification.handler import process_notification
from changedetectionio.notification_service import NotificationContextData, _check_cascading_vars
from loguru import logger
import datetime
import pytz
import re


BAD_CHARS_REGEX = r'[\x00-\x08\x0B\x0C\x0E-\x1F]'


def get_rss_template(datastore, watch, rss_content_format, default_html, default_plaintext):
    """Get the appropriate template for RSS content."""
    if datastore.data['settings']['application'].get('rss_template_type') == 'notification_body':
        return _check_cascading_vars(datastore=datastore, var_name='notification_body', watch=watch)

    override = datastore.data['settings']['application'].get('rss_template_override')
    if override and override.strip():
        return override
    elif 'text' in rss_content_format:
        return default_plaintext
    else:
        return default_html


def get_watch_label(datastore, watch):
    """Get the label for a watch based on settings."""
    if datastore.data['settings']['application']['ui'].get('use_page_title_in_list') or watch.get('use_page_title_in_list'):
        return watch.label
    else:
        return watch.get('url')


def add_watch_categories(fe, watch, datastore):
    """Add category tags to a feed entry based on watch tags."""
    for tag_uuid in watch.get('tags', []):
        tag = datastore.data['settings']['application'].get('tags', {}).get(tag_uuid)
        if tag and tag.get('title'):
            fe.category(term=tag.get('title'))


def build_notification_context(watch, timestamp_from, timestamp_to, watch_label,
                               n_body_template, rss_content_format):
    """Build the notification context object."""
    return NotificationContextData(initial_data={
        'notification_urls': ['null://just-sending-a-null-test-for-the-render-in-RSS'],
        'notification_body': n_body_template,
        'timestamp_to': timestamp_to,
        'timestamp_from': timestamp_from,
        'watch_label': watch_label,
        'notification_format': rss_content_format
    })


