from os import getenv
from copy import deepcopy

from changedetectionio.blueprint.menu_modes import MENU_SIDEBAR_ACTIONMODES_DEFAULT
from changedetectionio.blueprint.rss import RSS_FORMAT_TYPES, RSS_CONTENT_FORMAT_DEFAULT
from changedetectionio.model.Tags import TagsDict

from changedetectionio.notification import (
    default_notification_body,
    default_notification_format,
    default_notification_title,
)

# Equal to or greater than this number of FilterNotFoundInResponse exceptions will trigger a filter-not-found notification
_FILTER_FAILURE_THRESHOLD_ATTEMPTS_DEFAULT = 6
DEFAULT_SETTINGS_HEADERS_USERAGENT='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.66 Safari/537.36'



