"""
LLM fallback plugin for price and restock info extraction.

When the built-in structured-metadata extraction (JSON-LD, microdata, OpenGraph)
fails to produce both a price and availability, this plugin is called as a last
resort.  It sends a trimmed, HTML-stripped version of the page to the configured
LLM and asks it to return a structured JSON answer.

The module-level `datastore` variable is injected at startup by
`inject_datastore_into_plugins()` in pluggy_interface.py.
"""
import json
import os
import re
from loguru import logger
from changedetectionio.pluggy_interface import hookimpl
from changedetectionio.llm.evaluator import apply_local_token_multiplier

# Injected at startup by inject_datastore_into_plugins()
datastore = None

# JSON-LD blocks worth sending: only those that actually carry price/stock signals. This drops
# the noise (BreadcrumbList, WebSite, Organization, ItemList…) that otherwise dominates and
# pushes the useful data out of the (truncated) prompt.
_JSONLD_RELEVANT = re.compile(
    r'"(price|priceCurrency|lowPrice|highPrice|availability|offers|InStock|OutOfStock|priceSpecification)"',
    re.IGNORECASE,
)


def _extract_jsonld(html_content: str) -> str:
    """Extract the JSON-LD blocks that contain price/availability info (reliable structured
    product data). Blocks without any price/stock signal (breadcrumbs, site metadata, etc.)
    are skipped so they don't crowd out the useful content."""
    blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_content, flags=re.DOTALL | re.IGNORECASE
    )
    if not blocks:
        return ''
    relevant = [b.strip() for b in blocks if _JSONLD_RELEVANT.search(b)]
    combined = ' '.join(relevant)
    return combined[:2000]


