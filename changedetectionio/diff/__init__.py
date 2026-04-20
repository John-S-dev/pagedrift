"""
Diff rendering module for change detection.

This module provides functions for rendering differences between text content,
with support for various output formats and tokenization strategies.
"""

import difflib
from typing import List, Iterator, Union
from loguru import logger
import diff_match_patch as dmp_module
import re
import time

from .tokenizers import TOKENIZERS, tokenize_words_and_html

# Remember! gmail, outlook etc dont support <style> must be inline.
# Gmail: strips <ins> and <del> tags entirely.
# This is for the WHOLE line background style
REMOVED_STYLE = "background-color: #fadad7; color: #b30000;"
ADDED_STYLE = "background-color: #eaf2c2; color: #406619;"
HTML_REMOVED_STYLE = REMOVED_STYLE  # Export alias for handler.py
HTML_ADDED_STYLE = ADDED_STYLE      # Export alias for handler.py

# Darker backgrounds for nested highlighting (changed parts within lines)
REMOVED_INNER_STYLE = "background-color: #ff867a; color: #111;"
ADDED_INNER_STYLE = "background-color: #b2e841; color: #444;"
HTML_CHANGED_STYLE = REMOVED_STYLE
HTML_CHANGED_INTO_STYLE = ADDED_STYLE

# Placemarker constants - these get replaced by apply_service_tweaks() in handler.py
# Something that cant get escaped to HTML by accident
REMOVED_PLACEMARKER_OPEN = '@removed_PLACEMARKER_OPEN'
REMOVED_PLACEMARKER_CLOSED = '@removed_PLACEMARKER_CLOSED'

ADDED_PLACEMARKER_OPEN = '@added_PLACEMARKER_OPEN'
ADDED_PLACEMARKER_CLOSED = '@added_PLACEMARKER_CLOSED'

CHANGED_PLACEMARKER_OPEN = '@changed_PLACEMARKER_OPEN'
CHANGED_PLACEMARKER_CLOSED = '@changed_PLACEMARKER_CLOSED'

CHANGED_INTO_PLACEMARKER_OPEN = '@changed_into_PLACEMARKER_OPEN'
CHANGED_INTO_PLACEMARKER_CLOSED = '@changed_into_PLACEMARKER_CLOSED'

