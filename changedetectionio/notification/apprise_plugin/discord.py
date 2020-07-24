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

# Discord embed sidebar colors for different change types
DISCORD_COLOR_UNCHANGED = 8421504   # Gray (#808080)
DISCORD_COLOR_REMOVED = 16711680    # Red (#FF0000)
DISCORD_COLOR_ADDED = 65280         # Green (#00FF00)
DISCORD_COLOR_CHANGED = 16753920    # Orange (#FFA500)
DISCORD_COLOR_CHANGED_INTO = 3447003  # Blue (#5865F2 - Discord blue)
DISCORD_COLOR_WARNING = 16776960    # Yellow (#FFFF00)


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

        while position < len(body):
            # Find the next marker
            next_removed = body.find(REMOVED_PLACEMARKER_OPEN, position)
            next_added = body.find(ADDED_PLACEMARKER_OPEN, position)
            next_changed = body.find(CHANGED_PLACEMARKER_OPEN, position)
            next_changed_into = body.find(CHANGED_INTO_PLACEMARKER_OPEN, position)

            # Determine which marker comes first
            if next_removed == -1 and next_added == -1 and next_changed == -1 and next_changed_into == -1:
                # No more markers, rest is unchanged
                if position < len(body):
                    chunks.append(("unchanged", body[position:]))
                break

            # Find the earliest marker
            next_marker_pos = None
            next_marker_type = None

            # Compare all marker positions to find the earliest
            markers = []
            if next_removed != -1:
                markers.append((next_removed, "removed"))
            if next_added != -1:
                markers.append((next_added, "added"))
            if next_changed != -1:
                markers.append((next_changed, "changed"))
            if next_changed_into != -1:
                markers.append((next_changed_into, "changed_into"))

            if markers:
                next_marker_pos, next_marker_type = min(markers, key=lambda x: x[0])

            # Add unchanged content before the marker
            if next_marker_pos > position:
                chunks.append(("unchanged", body[position:next_marker_pos]))

            # Find the closing marker
            if next_marker_type == "removed":
                open_marker = REMOVED_PLACEMARKER_OPEN
                close_marker = REMOVED_PLACEMARKER_CLOSED
            elif next_marker_type == "added":
                open_marker = ADDED_PLACEMARKER_OPEN
                close_marker = ADDED_PLACEMARKER_CLOSED
            elif next_marker_type == "changed":
                open_marker = CHANGED_PLACEMARKER_OPEN
                close_marker = CHANGED_PLACEMARKER_CLOSED
            else:  # changed_into
                open_marker = CHANGED_INTO_PLACEMARKER_OPEN
                close_marker = CHANGED_INTO_PLACEMARKER_CLOSED

            close_pos = body.find(close_marker, next_marker_pos)

            if close_pos == -1:
                # No closing marker, take rest as this type
                content = body[next_marker_pos + len(open_marker):]
                chunks.append((next_marker_type, content))
                break
            else:
                # Extract content between markers
                content = body[next_marker_pos + len(open_marker):close_pos]
                chunks.append((next_marker_type, content))
                position = close_pos + len(close_marker)

        return chunks


