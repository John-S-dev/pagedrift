from functools import lru_cache, wraps

from loguru import logger
from typing import List
import html
import json
import os
import re
import threading

# ---------------------------------------------------------------------------------------
# libxml2 (lxml) concurrency guard
#
# Watch checks run run_changedetection() on a shared ThreadPoolExecutor
# (worker_pool.queue_executor), so extraction for different watches parses HTML in parallel
# threads. A single check uses TWO different lxml parsers: xpath_filter() builds its own
# etree.HTMLParser(), while html_to_text() -> inscriptis parses with lxml's process-global
# html_parser. lxml locks per parser OBJECT, so many threads on the SAME parser serialise
# safely - but that lock does not span two DIFFERENT parsers, and they still share libxml2's
# interned-string dictionary. Concurrent parses corrupt it, and the rendered text of one
# watch's page ends up inside another watch's snapshot.
#
# lxml's FAQ sanctions exactly two patterns: "the default parser (which is replicated for
# each thread) or create a parser for each thread yourself". A parser per CALL is neither -
# but note that a parser per THREAD does not fix this either (measured: still leaks), because
# inscriptis picks its own parser internally and we cannot redirect it. Serialising is the
# only configuration measured clean.
#
# Serialising is measured to be free: extraction is ~80ms mean / 204ms p95 over real data,
# a ceiling of ~12 checks/sec against the ~0.5 checks/sec that browser fetches can feed.
# It also HALVES peak RSS on large pages (481MB -> 232MB on a 3.85MB page across 7 threads),
# because only one libxml2 document is ever live.
#
# EVERY lxml entry point in this process must go through here - a single unguarded parse in
# any thread (Flask request, worker) is enough to reintroduce the corruption.
#
# This is a threading lock, not an asyncio one, and that is deliberate: nothing here is called
# from a coroutine. The async workers hand run_changedetection() to a ThreadPoolExecutor
# (worker.py: "Run change detection in executor to avoid blocking event loop"), the requests
# fetcher does the same, and Flask is synchronous. If you ever call a guarded function directly
# from a coroutine you will stall that worker's event loop for the duration of someone else's
# parse - bounded and deadlock-free (the holder is pure CPU and never awaits), but avoid it.
#
# Re-entrant: these helpers call into each other (element_removal -> subtractive_xpath_selector).
#
# LXML_LOCK_DISABLED=true removes the guard. It exists so the corruption can be reproduced on
# demand (see tests/test_lxml_concurrency.py) - it is NOT a tuning option, it reinstates a
# data-integrity bug that silently writes one watch's page text into another watch's snapshot.
def _build_lxml_lock():
    from changedetectionio.strtobool import strtobool

    if not strtobool(os.getenv('LXML_LOCK_DISABLED', 'false')):
        return threading.RLock()

    logger.warning("LXML_LOCK_DISABLED=true - lxml parsing is unguarded. Under concurrency this "
                   "is known to leak one watch's rendered page text into another watch's "
                   "snapshot. For testing only, never run this in production.")

    class _NullLock:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    return _NullLock()


_LXML_LOCK = _build_lxml_lock()


def lxml_guarded(fn):
    """Serialise a function's libxml2 work - parse, xpath traversal, tostring() and clear()
    all touch the document, so the whole call is held, not just the parse."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with _LXML_LOCK:
            return fn(*args, **kwargs)
    return wrapper


def lxml_guard():
    """Context manager for code OUTSIDE this module that drives lxml directly, so it shares the
    same lock (e.g. XPath validation in forms.py, which runs on Flask request threads)."""
    return _LXML_LOCK


def lxml_html_parser():
    """A fresh parser for each call, freed immediately afterwards. Never lxml's process-global
    default parser, which is shared across every thread."""
    from lxml import etree
    return etree.HTMLParser()

# ---------------------------------------------------------------------------------------

# HTML added to be sure each result matching a filter (.example) gets converted to a new line by Inscriptis
TEXT_FILTER_LIST_LINE_SUFFIX = "<br>"
TRANSLATE_WHITESPACE_TABLE = str.maketrans('', '', '\r\n\t ')
PERL_STYLE_REGEX = r'^/(.*?)/([a-z]*)?$'

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
META_CS  = re.compile(r'<meta[^>]+charset=["\']?\s*([a-z0-9_\-:+.]+)', re.I)

# jq builtins that can leak sensitive data or cause harm when user-supplied expressions are executed.
# env/$ENV reads all process environment variables (passwords, API keys, etc.)
# include/import can read arbitrary files from disk
# input/inputs reads beyond the supplied JSON data
# debug/stderr leaks data to stderr
# halt/halt_error terminates the process (DoS)
_JQ_BLOCKED_PATTERNS = [
    (re.compile(r'\benv\b'),                    'env (reads environment variables)'),
    (re.compile(r'\$ENV\b'),                    '$ENV (reads environment variables)'),
    (re.compile(r'\binclude\b'),                'include (reads files from disk)'),
    (re.compile(r'\bimport\b'),                 'import (reads files from disk)'),
    (re.compile(r'\binputs?\b'),                'input/inputs (reads beyond provided data)'),
    (re.compile(r'\bdebug\b'),                  'debug (leaks data to stderr)'),
    (re.compile(r'\bstderr\b'),                 'stderr (leaks data to stderr)'),
    (re.compile(r'\bhalt(?:_error)?\b'),        'halt/halt_error (terminates the process)'),
    (re.compile(r'\$__loc__\b'),                '$__loc__ (leaks file path information)'),
    (re.compile(r'\bbuiltins\b'),               'builtins (enumerates available functions)'),
    (re.compile(r'\bmodulemeta\b'),             'modulemeta (leaks module information)'),
    (re.compile(r'\$JQ_BUILD_CONFIGURATION\b'), '$JQ_BUILD_CONFIGURATION (leaks build information)'),
]

def validate_jq_expression(expression: str) -> None:
    """Raise ValueError if the jq expression uses any dangerous builtin.

    User-supplied jq expressions are executed server-side. Without this check,
    builtins like `env` expose every process environment variable (SALTED_PASS,
    proxy credentials, API keys, etc.) as watch output.
    """
    from changedetectionio.strtobool import strtobool
    if strtobool(os.getenv('JQ_ALLOW_RISKY_EXPRESSIONS', 'false')):
        return

    for pattern, description in _JQ_BLOCKED_PATTERNS:
        if pattern.search(expression):
            msg = f"jq expression uses disallowed builtin: {description}"
            logger.critical(f"Security: blocked jq expression containing '{description}' - expression: {expression!r}")
            raise ValueError(msg)

META_CT  = re.compile(r'<meta[^>]+http-equiv=["\']?content-type["\']?[^>]*content=["\'][^>]*charset=([a-z0-9_\-:+.]+)', re.I)

# 'price' , 'lowPrice', 'highPrice' are usually under here
# All of those may or may not appear on different websites - I didnt find a way todo case-insensitive searching here
LD_JSON_PRODUCT_OFFER_SELECTORS = ["json:$..offers", "json:$..Offers"]

def get_safe_xpath3_parser():
    """Return an XPath3Parser subclass with filesystem/environment access functions removed.

    XPath 3.0 includes functions that can read arbitrary files or environment variables:
      - unparsed-text / unparsed-text-lines / unparsed-text-available  (file read)
      - doc / doc-available                                             (XML fetch from URI)
      - environment-variable / available-environment-variables         (env var leakage)

    Subclassing gives us an independent symbol_table copy (not shared with the parent class),
    so removing entries here does not affect XPath3Parser itself.

    Override the blocked list via the XPATH_BLOCKED_FUNCTIONS environment variable
    (comma-separated, e.g. "unparsed-text,doc,environment-variable").
    """
    import os
    from elementpath.xpath3 import XPath3Parser

    class SafeXPath3Parser(XPath3Parser):
        pass

    env_override = os.getenv('XPATH_BLOCKED_FUNCTIONS')
    if env_override is not None:
        blocked = [f.strip() for f in env_override.split(',') if f.strip()]
    else:
        blocked = _DEFAULT_UNSAFE_XPATH3_FUNCTIONS

    for _fn in blocked:
        SafeXPath3Parser.symbol_table.pop(_fn, None)

    return SafeXPath3Parser


# Doesn't look like python supports forward slash auto enclosure in re.findall
# So convert it to inline flag "(?i)foobar" type configuration
@lru_cache(maxsize=100)
def perl_style_slash_enclosed_regex_to_options(regex):

    res = re.search(PERL_STYLE_REGEX, regex, re.IGNORECASE)

    if res:
        flags = res.group(2) if res.group(2) else 'i'
        regex = f"(?{flags}){res.group(1)}"
    else:
        # Fall back to just ignorecase as an option
        regex = f"(?i){regex}"

    return regex

# Return str Utf-8 of matched rules
# 'xpath1:'
@lxml_guarded
def xpath1_filter(xpath_filter, html_content, append_pretty_line_formatting=False, is_xml=False):
    from lxml import etree, html

    # Own parser, not lxml's process-global default (which parser=None would select).
    parser = lxml_html_parser()
    tree = None
    try:
        if is_xml:
            # So that we can keep CDATA for cdata_in_document_to_text() to process
            parser = etree.XMLParser(strip_cdata=False, resolve_entities=False, no_network=True)
            # For XML/RSS content, use etree.fromstring to properly handle XML declarations
            tree = etree.fromstring(html_content.encode('utf-8') if isinstance(html_content, str) else html_content, parser=parser)
        else:
            tree = html.fromstring(html_content, parser=parser)
        html_block = ""

        # Build namespace map for XPath queries
        namespaces = {'re': 'http://exslt.org/regular-expressions'}

        # NOTE: lxml's native xpath() does NOT support empty string prefix for default namespace
        # For documents with default namespace (RSS/Atom feeds), users must use:
        #   - local-name(): //*[local-name()='title']/text()
        #   - Or use xpath_filter (not xpath1_filter) which supports default namespaces
        # XPath spec: unprefixed element names have no namespace, not the default namespace

        r = tree.xpath(xpath_filter.strip(), namespaces=namespaces)
        #@note: xpath1 (lxml) does NOT automatically handle default namespaces
        #@note: Use //*[local-name()='element'] or switch to xpath_filter for default namespace support
        #@note: //title/text() wont work where <title>CDATA.. (use cdata_in_document_to_text first)

        for element in r:
            # When there's more than 1 match, then add the suffix to separate each line
            # And where the matched result doesn't include something that will cause Inscriptis to add a newline
            # (This way each 'match' reliably has a new-line in the diff)
            # Divs are converted to 4 whitespaces by inscriptis
            if append_pretty_line_formatting and len(html_block) and (not hasattr(element, 'tag') or not element.tag in (['br', 'hr', 'div', 'p'])):
                html_block += TEXT_FILTER_LIST_LINE_SUFFIX

            # Some kind of text, UTF-8 or other
            if isinstance(element, (str, bytes)):
                html_block += element
            else:
                # Return the HTML/XML which will get parsed as text
                # Use 'xml' method for RSS/XML content, 'html' for HTML content
                # parser will be XMLParser if we detected XML content
                method = 'xml' if (is_xml or isinstance(parser, etree.XMLParser)) else 'html'
                html_block += etree.tostring(element, pretty_print=True, method=method, encoding='unicode')

        return html_block
    finally:
        # Explicitly clear the tree to free memory
        # lxml trees can hold significant memory, especially with large documents
        if tree is not None:
            tree.clear()

# Extract/find element
def extract_element(find='title', html_content=''):
    from bs4 import BeautifulSoup

    #Re #106, be sure to handle when its not found
    element_text = None

    soup = BeautifulSoup(html_content, 'html.parser')
    result = soup.find(find)
    if result and result.string:
        element_text = result.string.strip()

    return element_text

