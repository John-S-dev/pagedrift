"""Which content fetchers can drive the Add-Watch live preview / visual selector.

Single source of truth for "can this browser render a live preview": the Add-Watch
browser list, the /snapshot endpoint and the submit-time form validator all resolve
through here, so the UI can never offer - and the server can never accept - a fetcher
that is unable to produce what the visual selector needs.

The preview is rendered by browsersteps_live_ui() (see blueprint/browser_steps), so a
usable browser needs `supports_browser_steps` *as well as* screenshots and xpath
element data. That third flag is what rules out Selenium/WebDriver: it can screenshot
during a normal check, but it cannot drive the interactive session the preview needs
(acquire_browser_for_fetcher() would quietly connect to PLAYWRIGHT_DRIVER_URL instead,
which is not the browser the user picked). It also rules out settings.requests
extra_browsers, which are WebDriver connection URLs, so they are not offered here.
"""

from loguru import logger

SYSTEM_DEFAULT = 'system'

# Every flag a fetcher must set to be usable for the Add-Watch live preview.
REQUIRED_CAPABILITIES = (
    'supports_browser_steps',
    'supports_screenshots',
    'supports_xpath_element_data',
)


def is_visual_capable(fetch_backend, datastore):
    """True when this backend can render the Add-Watch live preview.

    An unknown name - including anything a client made up - resolves to no fetcher
    class and so to all-False capabilities, so it can never pass. That is what makes
    the posted value safe without any string filtering of our own.

    Reads the flags off the class the same way Watch.fetcher_supports_screenshots does,
    rather than via pluggy_interface.get_fetcher_capabilities(): that logs every lookup
    at INFO, and this runs for the whole fetcher list on any page carrying the quick-add
    form. Plugin fetchers are registered as module attributes, so they resolve here too.
    """
    from changedetectionio import content_fetchers
    from changedetectionio.content_fetchers.base import FetcherCapabilities

    name = fetch_backend or SYSTEM_DEFAULT
    if name == SYSTEM_DEFAULT:
        name = datastore.data['settings']['application'].get('fetch_backend') or 'html_requests'

    caps = FetcherCapabilities.from_fetcher(getattr(content_fetchers, name, None))
    missing = [flag for flag in REQUIRED_CAPABILITIES if not getattr(caps, flag, False)]
    logger.debug(f"Add-watch browser '{fetch_backend or SYSTEM_DEFAULT}' -> '{name}': "
                 f"{', '.join(f'{k}={v}' for k, v in caps.model_dump().items())} - "
                 f"{'usable for live preview' if not missing else 'not offered, missing ' + ', '.join(missing)}")
    return not missing


def system_default_description(datastore):
    """Label for whatever backend 'system' currently points at."""
    from changedetectionio import content_fetchers

    system_backend = datastore.data['settings']['application'].get('fetch_backend') or 'html_requests'
    return str(dict(content_fetchers.available_fetchers()).get(system_backend, system_backend))


def radio_choices(datastore):
    """(value, label) for the Add-Watch browser radio list, system default first.

    'System settings default' is always listed - with the reason in its own label when
    the global default cannot render a preview, because greying it out explains why it
    is unavailable where silently dropping it does not. Which entries are unusable is
    reported separately by unusable_values(); WTForms cannot carry per-option render_kw
    through a RadioField, so the disabled attribute is applied when rendering.
    """
    from flask_babel import gettext

    described = system_default_description(datastore)

    if is_visual_capable(SYSTEM_DEFAULT, datastore):
        system_label = gettext('System settings default (%(browser)s)', browser=described)
    else:
        system_label = gettext('System settings default (%(browser)s - no live preview)', browser=described)

    return [(SYSTEM_DEFAULT, system_label)] + list_visual_browser_choices(datastore)


def unusable_values(datastore):
    """Values that are listed for explanation only and must render disabled."""
    return set() if is_visual_capable(SYSTEM_DEFAULT, datastore) else {SYSTEM_DEFAULT}
