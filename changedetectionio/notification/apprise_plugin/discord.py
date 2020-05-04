"""
Custom Discord plugin for changedetection.io
Extends Apprise's Discord plugin to support custom colored embeds for removed/added content
"""
from apprise.plugins.discord import NotifyDiscord
from apprise.decorators import notify
from apprise.common import NotifyFormat
from loguru import logger

# Import placeholders from changedetection's diff module
from ...diff import (
    REMOVED_PLACEMARKER_OPEN,
    REMOVED_PLACEMARKER_CLOSED,
    ADDED_PLACEMARKER_OPEN,
    ADDED_PLACEMARKER_CLOSED,
    CHANGED_PLACEMARKER_OPEN,
    CHANGED_PLACEMARKER_CLOSED,
    CHANGED_INTO_PLACEMARKER_OPEN,
    CHANGED_INTO_PLACEMARKER_CLOSED,
)

class NotifyDiscordCustom(NotifyDiscord):
    """
    Custom Discord notification handler that supports multiple colored embeds
    for showing removed (red) and added (green) content separately.
    """

    def send(self, body, title="", notify_type=None, attach=None, **kwargs):
        """
        Override send method to create custom embeds with red/green colors
        for removed/added content when placeholders are present.
        """

        # Check if body contains our diff placeholders
        has_removed = REMOVED_PLACEMARKER_OPEN in body
        has_added = ADDED_PLACEMARKER_OPEN in body
        has_changed = CHANGED_PLACEMARKER_OPEN in body
        has_changed_into = CHANGED_INTO_PLACEMARKER_OPEN in body

        # If we have diff placeholders and we're in markdown/html format, create custom embeds
        if (has_removed or has_added or has_changed or has_changed_into) and self.notify_format in (NotifyFormat.MARKDOWN, NotifyFormat.HTML):
            return self._send_with_colored_embeds(body, title, notify_type, attach, **kwargs)

        # Otherwise, use the parent class's default behavior
        return super().send(body, title, notify_type, attach, **kwargs)

    def _send_with_colored_embeds(self, body, title, notify_type, attach, **kwargs):
        """
        Send Discord message with embeds in the original diff order.
        Preserves the sequence: unchanged -> removed -> added -> unchanged, etc.
        """
        from datetime import datetime, timezone

        payload = {
            "tts": self.tts,
            "wait": self.tts is False,
        }

        if self.flags:
            payload["flags"] = self.flags

        # Acquire image_url
        image_url = self.image_url(notify_type)

        if self.avatar and (image_url or self.avatar_url):
            payload["avatar_url"] = self.avatar_url if self.avatar_url else image_url

