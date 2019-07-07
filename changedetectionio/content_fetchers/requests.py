from flask_babel import lazy_gettext as _l
from loguru import logger
from urllib.parse import urljoin, urlparse
import hashlib
import os
import re
import asyncio

from changedetectionio import strtobool
from changedetectionio.content_fetchers.exceptions import BrowserStepsInUnsupportedFetcher, EmptyReply, Non200ErrorCodeReceived
from changedetectionio.content_fetchers.base import Fetcher
from changedetectionio.validate_url import is_fetch_url_allowed, is_private_hostname, is_url_private_or_parser_confused


# "html_requests" is listed as the default fetcher in store.py!
class fetcher(Fetcher):
    fetcher_description = _l("Basic fast Plaintext/HTTP Client")

    def __init__(self, proxy_override=None, custom_browser_connection_url=None, **kwargs):
        super().__init__(**kwargs)
        self.proxy_override = proxy_override
        # browser_connection_url is none because its always 'launched locally'

    def _run_sync(self,
            url,
            timeout,
            request_headers,
            request_body,
            request_method,
            ignore_status_codes=False,
            current_include_filters=None,
            is_binary=False,
            empty_pages_are_a_change=False,
            watch_uuid=None,
            ):
        """Synchronous version of run - the original requests implementation"""

        import chardet
        import requests
        from requests.exceptions import ProxyError, ConnectionError, RequestException

        if self.browser_steps:
            raise BrowserStepsInUnsupportedFetcher(url=url)

        proxies = {}

        # Allows override the proxy on a per-request basis
        # https://requests.readthedocs.io/en/latest/user/advanced/#socks
        # Should also work with `socks5://user:pass@host:port` type syntax.

