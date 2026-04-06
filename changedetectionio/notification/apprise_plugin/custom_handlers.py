"""
Custom Apprise HTTP Handlers with format= Parameter Support

IMPORTANT: This module works around a limitation in Apprise's @notify decorator.

THE PROBLEM:
-------------
When using Apprise's @notify decorator to create custom notification handlers, the
decorator creates a CustomNotifyPlugin that uses parse_url(..., simple=True) to parse
URLs. This simple parsing mode does NOT extract the format= query parameter from the URL
and set it as a top-level parameter that NotifyBase.__init__ can use to set notify_format.

As a result:
1. URL: post://example.com/webhook?format=html
2. Apprise parses this and sees format=html in qsd (query string dictionary)
3. But it does NOT extract it and pass it to NotifyBase.__init__
4. NotifyBase defaults to notify_format=TEXT
5. When you call apobj.notify(body="<html>...", body_format="html"):
   - Apprise sees: input format = html, output format (notify_format) = text
   - Apprise calls convert_between("html", "text", body)
   - This strips all HTML tags, leaving only plain text
6. Your custom handler receives stripped plain text instead of HTML

THE SOLUTION:
-------------
Instead of using the @notify decorator directly, we:
1. Manually register custom plugins using plugins.N_MGR.add()
2. Create a CustomHTTPHandler class that extends CustomNotifyPlugin
3. Override __init__ to extract format= from qsd and set it as kwargs['format']
4. Call NotifyBase.__init__ which properly sets notify_format from kwargs['format']
5. Set up _default_args like CustomNotifyPlugin does for compatibility

This ensures that when format=html is in the URL:
- notify_format is set to HTML
- Apprise sees: input format = html, output format = html
- No conversion happens (convert_between returns content unchanged)
- Your custom handler receives the original HTML intact

TESTING:
--------
To verify this works:
>>> apobj = apprise.Apprise()
>>> apobj.add('post://localhost:5005/test?format=html')
>>> for server in apobj:
...     print(server.notify_format)  # Should print: html (not text)
>>> apobj.notify(body='<span>Test</span>', body_format='html')
# Your handler should receive '<span>Test</span>' not 'Test'
"""

import json
import os
import re
from urllib.parse import unquote_plus, urlparse

import requests
from apprise import plugins
from apprise.decorators.base import CustomNotifyPlugin
from apprise.utils.parse import parse_url as apprise_parse_url, url_assembly
from apprise.utils.logic import dict_full_update
from loguru import logger
from requests.structures import CaseInsensitiveDict

from changedetectionio.validate_url import is_private_hostname, is_url_private_or_parser_confused

SUPPORTED_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head"}


def notify_supported_methods(func):
    """Register custom HTTP method handlers that properly support format= parameter."""
    for method in SUPPORTED_HTTP_METHODS:
        _register_http_handler(method, func)
        _register_http_handler(f"{method}s", func)
    return func


def _get_params(parsed_url: dict) -> CaseInsensitiveDict:
    # https://github.com/caronc/apprise/wiki/Notify_Custom_JSON#get-parameter-manipulation
    # In Apprise, it relies on prefixing each request arg with "-", because it uses say &method=update as a flag for apprise
    # but here we are making straight requests, so we need todo convert this against apprise's logic
    params = CaseInsensitiveDict(
        {
            unquote_plus(k): unquote_plus(v)
            for k, v in parsed_url["qsd"].items()
            if k.strip("-") not in parsed_url["qsd-"]
            and k.strip("+") not in parsed_url["qsd+"]
        }
    )

    return params


@notify_supported_methods
def apprise_http_custom_handler(
    body: str,
    title: str,
    notify_type: str,
    meta: dict,
    body_format: str = None,
    *args,
    **kwargs,
) -> bool:


    url: str = meta.get("url")
    schema: str = meta.get("schema")
    method: str = re.sub(r"s$", "", schema).upper()

    # Convert /foobar?+some-header=hello to proper header dictionary
    parsed_url: dict[str, str | dict | None] | None = apprise_parse_url(url)
    if parsed_url is None:
        return False

    auth = _get_auth(parsed_url=parsed_url)
    headers = _get_headers(parsed_url=parsed_url, body=body)
    params = _get_params(parsed_url=parsed_url)

    url = re.sub(rf"^{schema}", "https" if schema.endswith("s") else "http", parsed_url.get("url"))

    # SSRF protection — block private/loopback addresses unless explicitly allowed.
    # Uses parser-agnostic check so urlparse/urllib3 differentials (GHSA-rph4-96w6-q594)
    # can't smuggle an internal target past the gate.
    if not os.getenv('ALLOW_IANA_RESTRICTED_ADDRESSES', '').lower() in ('true', '1', 'yes'):
        if is_url_private_or_parser_confused(url):
            raise ValueError(
                f"Notification target '{url}' is a private/reserved address "
                f"or contains a parser-differential payload. "
                f"Set ALLOW_IANA_RESTRICTED_ADDRESSES=true to allow."
            )

    response = requests.request(
        method=method,
        url=url,
        auth=auth,
        headers=headers,
        params=params,
        data=body.encode("utf-8") if isinstance(body, str) else body,
    )

    response.raise_for_status()

    logger.info(f"Successfully sent custom notification to {url}")
    return True
