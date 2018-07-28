import sys
from changedetectionio.strtobool import strtobool
from loguru import logger
from changedetectionio.content_fetchers.exceptions import BrowserStepsStepException
import os

# Visual Selector scraper - 'Button' is there because some sites have <button>OUT OF STOCK</button>.
visualselector_xpath_selectors = 'div,span,form,table,tbody,tr,td,a,p,ul,li,h1,h2,h3,h4,header,footer,section,article,aside,details,main,nav,section,summary,button'

# available_fetchers() will scan this implementation looking for anything starting with html_
# this information is used in the form selections
from changedetectionio.content_fetchers.requests import fetcher as html_requests


import importlib.resources
XPATH_ELEMENT_JS = importlib.resources.files("changedetectionio.content_fetchers.res").joinpath('xpath_element_scraper.js').read_text(encoding='utf-8')
INSTOCK_DATA_JS = importlib.resources.files("changedetectionio.content_fetchers.res").joinpath('stock-not-in-stock.js').read_text(encoding='utf-8')
FAVICON_FETCHER_JS = importlib.resources.files("changedetectionio.content_fetchers.res").joinpath('favicon-fetcher.js').read_text(encoding='utf-8')


def available_fetchers():
    # See the if statement at the bottom of this file for how we switch between playwright and webdriver
    import inspect
    p = []

    # Get built-in fetchers (but skip plugin fetchers that were added via setattr)
    for name, obj in inspect.getmembers(sys.modules[__name__], inspect.isclass):
        if inspect.isclass(obj):
            # @todo html_ is maybe better as fetcher_ or something
            # In this case, make sure to edit the default one in store.py and fetch_site_status.py
            if name.startswith('html_'):
                # Skip plugin fetchers that were already registered
                if name not in _plugin_fetchers:
                    t = tuple([name, obj.fetcher_description])
                    p.append(t)

    # Get plugin fetchers from cache (already loaded at module init)
    for name, fetcher_class in _plugin_fetchers.items():
        if hasattr(fetcher_class, 'fetcher_description'):
            t = tuple([name, fetcher_class.fetcher_description])
            p.append(t)
        else:
            logger.warning(f"Plugin fetcher '{name}' does not have fetcher_description attribute")

    return p


def get_plugin_fetchers():
    """Load and return all plugin fetchers from the centralized plugin manager."""
    from changedetectionio.pluggy_interface import plugin_manager

    fetchers = {}
    try:
        # Call the register_content_fetcher hook from all registered plugins
        results = plugin_manager.hook.register_content_fetcher()
        for result in results:
            if result:
                name, fetcher_class = result
                fetchers[name] = fetcher_class
                # Register in current module so hasattr() checks work
                setattr(sys.modules[__name__], name, fetcher_class)
                logger.info(f"Registered plugin fetcher: {name} - {getattr(fetcher_class, 'fetcher_description', 'No description')}")
    except Exception as e:
        logger.error(f"Error loading plugin fetchers: {e}")

    return fetchers


