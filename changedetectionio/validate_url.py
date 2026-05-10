import ipaddress
import socket
from functools import lru_cache
from loguru import logger
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, quote, unquote


def normalize_url_encoding(url):
    """
    Safely encode a URL's query parameters, regardless of whether they're already encoded.

    Why this is necessary:
    URLs can arrive in various states - some with already encoded query parameters (%20 for spaces),
    some with unencoded parameters (literal spaces), or a mix of both. The validators.url() function
    requires proper encoding, but simply encoding an already-encoded URL would double-encode it
    (e.g., %20 would become %2520).

    This function solves the problem by:
    1. Parsing the URL to extract query parameters
    2. parse_qsl() automatically decodes parameters if they're encoded
    3. urlencode() re-encodes them properly
    4. Returns a consistently encoded URL that will pass validation

    Example:
    - Input:  "http://example.com/test?time=2025-10-28 09:19"  (space not encoded)
    - Output: "http://example.com/test?time=2025-10-28+09%3A19" (properly encoded)

    - Input:  "http://example.com/test?time=2025-10-28%2009:19" (already encoded)
    - Output: "http://example.com/test?time=2025-10-28+09%3A19" (properly encoded)

    Returns a properly encoded URL string.
    """
    try:
        # Parse the URL into components (scheme, netloc, path, params, query, fragment)
        parsed = urlparse(url)

        # Parse query string - this automatically decodes it if encoded
        # parse_qsl handles both encoded and unencoded query strings gracefully
        query_params = parse_qsl(parsed.query, keep_blank_values=True)

        # Re-encode the query string properly using standard URL encoding
        encoded_query = urlencode(query_params, safe='')

        # Fragments need the same treatment - browsers accept characters there that
        # RFC 3986 does not (e.g. '|' in "...w-4#int=S:PFreco|PF|48966", see issue #4209)
        # and validators.url() would reject them. unquote() first so an already-encoded
        # fragment isn't double-encoded, then re-quote keeping every character that
        # RFC 3986 allows in a fragment (pchar / "/" / "?") intact.
        encoded_fragment = quote(unquote(parsed.fragment), safe="/?:@!$&'()*+,;=")

        # Reconstruct the URL with properly encoded query string
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            encoded_query,  # Use the re-encoded query
            encoded_fragment  # Use the re-encoded fragment
        ))

        return normalized
    except Exception as e:
        # If parsing fails for any reason, return original URL
        logger.debug(f"URL normalization failed for '{url}': {e}")
        return url


