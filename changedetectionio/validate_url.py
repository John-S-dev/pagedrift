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


def is_special_purpose_ip(ip):
    """Return (blocked: bool, why: str) for a single resolved IP address.

    THE one place that decides "is this address off-limits to the fetcher?". Everything
    that resolves a hostname must funnel through here so a newly-discovered range is
    added once, not once per call site.

    IPv6 addresses that embed an IPv4 address (IPv4-mapped, 6to4, Teredo) are unwrapped
    and re-checked, so e.g. ::ffff:100.64.0.1 cannot smuggle a blocked v4 address past a
    v6-only classification.
    """
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip)

    if ip.is_private:
        return True, 'private'
    if ip.is_loopback:
        return True, 'loopback'
    if ip.is_link_local:
        return True, 'link-local'
    if ip.is_reserved:
        return True, 'reserved'
    if ip.is_multicast:
        return True, 'multicast'
    if ip.is_unspecified:
        return True, 'unspecified'

    for net in _NON_GLOBAL_EXTRA_NETWORKS:
        if ip.version == net.version and ip in net:
            return True, f'in non-globally-reachable range {net}'

    # Catch-all for ranges this Python release knows are not globally reachable but which
    # none of the flags above expose (100.64.0.0/10 is such a case on CPython 3.12).
    if not ip.is_global:
        return True, 'not globally reachable'

    # An IPv6 address carrying an IPv4 payload is only as safe as that payload.
    for embedded in (getattr(ip, 'ipv4_mapped', None), getattr(ip, 'sixtofour', None), getattr(ip, 'teredo', None)):
        if embedded is None:
            continue
        # .teredo returns a (server, client) tuple; the others return a single address.
        for candidate in (embedded if isinstance(embedded, tuple) else (embedded,)):
            blocked, why = is_special_purpose_ip(candidate)
            if blocked:
                return True, f'embeds IPv4 address {candidate} ({why})'

    return False, ''


def is_private_hostname(hostname):
    """Return True if hostname resolves to an IANA-restricted (private/reserved/non-global) IP address.

    Unresolvable hostnames return False (allow them) — DNS may be temporarily unavailable
    or the domain not yet live. The actual DNS rebinding attack is mitigated by fetch-time
    re-validation in requests.py, not by blocking unresolvable domains at add-time.
    Never cached — callers that need fresh DNS resolution (e.g. at fetch time) can call
    this directly without going through the lru_cached is_safe_valid_url().

    A hostname is refused if ANY of its A/AAAA records is off-limits: a name that answers
    with one public and one CGNAT address is still a route to the CGNAT address.
    """
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            blocked, why = is_special_purpose_ip(ip)
            if blocked:
                logger.warning(f"Hostname '{hostname}' resolves to {ip} which is {why} — refused.")
                return True
    except socket.gaierror as e:
        logger.warning(f"{hostname} error checking {str(e)}")
        return False
    except ValueError as e:
        # getaddrinfo handed back something ip_address() won't parse - fail closed.
        logger.warning(f"Hostname '{hostname}' produced an unparseable address ({e}) — refused.")
        return True
    logger.info(f"Hostname '{hostname}' is NOT private/IANA restricted.")
    return False


