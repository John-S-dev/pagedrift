"""
Prompt construction for LLM evaluation calls.
Pure functions — no side effects, fully testable.
"""

import re

from .bm25_trim import trim_to_relevant

_AGO_RE = re.compile(r'^\d+\s+\w+\s+ago$', re.IGNORECASE)

