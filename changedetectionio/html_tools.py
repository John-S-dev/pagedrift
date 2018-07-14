from functools import lru_cache, wraps

from loguru import logger
from typing import List
import html
import json
import os
import re
import threading

def lxml_html_parser():
    """A fresh parser for each call, freed immediately afterwards. Never lxml's process-global
    default parser, which is shared across every thread."""
    from lxml import etree
    return etree.HTMLParser()

# ---------------------------------------------------------------------------------------

