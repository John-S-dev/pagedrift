"""
Pure Python metadata extractor - no lxml, no memory leaks.

This module provides a fast, memory-efficient alternative to extruct for common
e-commerce metadata extraction. It handles:
- JSON-LD (covers 80%+ of modern sites)
- OpenGraph meta tags
- Basic microdata attributes

Uses Python's built-in html.parser instead of lxml/libxml2, avoiding C-level
memory allocation issues. For edge cases, the main processor can fall back to
extruct (with subprocess isolation on Linux).
"""

from html.parser import HTMLParser
import json
import re
from loguru import logger


class OpenGraphExtractor(HTMLParser):
    """
    Extract OpenGraph meta tags from HTML.

    Finds <meta property="og:*"> tags commonly used for social media sharing.
    """

    def __init__(self):
        super().__init__()
        self.og_data = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs_dict = dict(attrs)
            prop = attrs_dict.get('property', '')

            # Extract OpenGraph properties
            if prop.startswith('og:'):
                content = attrs_dict.get('content', '')
                if content:
                    self.og_data[prop] = content


class MicrodataExtractor(HTMLParser):
    """
    Extract basic microdata attributes from HTML.

    Finds elements with itemprop attributes. This is a simplified extractor
    that doesn't handle nested itemscope/itemtype hierarchies - for complex
    cases, use extruct as fallback.
    """

    def __init__(self):
        super().__init__()
        self.microdata = {}
        self.current_itemprop = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if 'itemprop' in attrs_dict:
            itemprop = attrs_dict['itemprop']

            # Price/currency/availability can be in content/href attributes
            if itemprop == 'price':
                if 'content' in attrs_dict:
                    self.microdata['price'] = attrs_dict['content']
                else:
                    self.current_itemprop = 'price'

            elif itemprop == 'priceCurrency':
                if 'content' in attrs_dict:
                    self.microdata['currency'] = attrs_dict['content']
                else:
                    self.current_itemprop = 'priceCurrency'

            elif itemprop == 'availability':
                # Can be in href (link) or content (meta)
                if 'href' in attrs_dict:
                    self.microdata['availability'] = attrs_dict['href']
                elif 'content' in attrs_dict:
                    self.microdata['availability'] = attrs_dict['content']
                else:
                    self.current_itemprop = 'availability'

    def handle_data(self, data):
        # Capture text content for itemprop elements
        if self.current_itemprop == 'price':
            # Try to extract numeric price from text
            try:
                price_text = re.sub(r'[^\d.]', '', data.strip())
                if price_text:
                    self.microdata['price'] = float(price_text)
            except ValueError:
                pass
        elif self.current_itemprop == 'priceCurrency':
            currency = data.strip()
            if currency:
                self.microdata['currency'] = currency
        elif self.current_itemprop == 'availability':
            availability = data.strip()
            if availability:
                self.microdata['availability'] = availability

    def handle_endtag(self, tag):
        # Reset current itemprop after closing tag
        self.current_itemprop = None


