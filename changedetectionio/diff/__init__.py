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

# Compiled regex patterns for performance
WHITESPACE_NORMALIZE_RE = re.compile(r'\s+')

# Regexes built from the constants above — no brittle hardcoded strings
_EXTRACT_REMOVED_RE = re.compile(
    re.escape(REMOVED_PLACEMARKER_OPEN) + r'(.*?)' + re.escape(REMOVED_PLACEMARKER_CLOSED)
    + r'|' +
    re.escape(CHANGED_PLACEMARKER_OPEN) + r'(.*?)' + re.escape(CHANGED_PLACEMARKER_CLOSED)
)
_EXTRACT_ADDED_RE = re.compile(
    re.escape(ADDED_PLACEMARKER_OPEN) + r'(.*?)' + re.escape(ADDED_PLACEMARKER_CLOSED)
    + r'|' +
    re.escape(CHANGED_INTO_PLACEMARKER_OPEN) + r'(.*?)' + re.escape(CHANGED_INTO_PLACEMARKER_CLOSED)
)


def extract_changed_from(raw_diff: str) -> str:
    """Extract only the removed/changed-from fragments from a raw diff string.

    Useful for {{diff_changed_from}} — gives just the old value (e.g. old price),
    not the full surrounding line. Multiple fragments joined with newlines.
    """
    return '\n'.join(next((g for g in m.groups() if g is not None), '') for m in _EXTRACT_REMOVED_RE.finditer(raw_diff))


def render_nested_line_diff(before_line: str, after_line: str, ignore_junk: bool = False, tokenizer: str = 'words_and_html') -> tuple[str, str, bool]:
    """
    Render line-level differences with nested highlighting for changed parts.

    Returns two separate lines:
    - Before line: light red background with dark red on removed parts
    - After line: light green background with dark green on added parts

    Args:
        before_line: Original line text
        after_line: Modified line text
        ignore_junk: Ignore whitespace-only changes
        tokenizer: Name of tokenizer to use from TOKENIZERS registry

    Returns:
        tuple[str, str, bool]: (before_with_highlights, after_with_highlights, has_changes)
    """
    # Normalize whitespace if ignore_junk is enabled
    if ignore_junk:
        before_normalized = WHITESPACE_NORMALIZE_RE.sub(' ', before_line)
        after_normalized = WHITESPACE_NORMALIZE_RE.sub(' ', after_line)
    else:
        before_normalized = before_line
        after_normalized = after_line

    # Use diff-match-patch with word-level tokenization
    dmp = dmp_module.diff_match_patch()

    # Get the tokenizer function from the registry
    tokenizer_func = TOKENIZERS.get(tokenizer, tokenize_words_and_html)

    # Tokenize both lines
    before_tokens = tokenizer_func(before_normalized)
    after_tokens = tokenizer_func(after_normalized or ' ')

    # Create mappings for linesToChars
    before_text = '\n'.join(before_tokens)
    after_text = '\n'.join(after_tokens)

    # Use linesToChars for word-mode diffing
    lines_result = dmp.diff_linesToChars(before_text, after_text)
    line_before, line_after, line_array = lines_result

    # Perform diff on the encoded strings
    diffs = dmp.diff_main(line_before, line_after, False)

    # Convert back to original text
    dmp.diff_charsToLines(diffs, line_array)

    # Remove the newlines we added for tokenization
    diffs = [(op, text.replace('\n', '')) for op, text in diffs]

    # DON'T apply semantic cleanup here - it would break token boundaries
    # (e.g., "63" -> "66" would become "6" + "3" vs "6" + "6")
    # We want to preserve the tokenizer's word boundaries

    # Check if there are any changes
    has_changes = any(op != 0 for op, _ in diffs)

    if ignore_junk and not has_changes:
        return before_line, after_line, False

    # Build the before line (with nested highlighting for removed parts)
    before_parts = []
    for op, text in diffs:
        if op == 0:  # Equal
            before_parts.append(text)
        elif op == -1:  # Deletion (in before)
            before_parts.append(f'<span style="{REMOVED_INNER_STYLE}">{text}</span>')
        # Skip insertions (op == 1) for the before line

    before_content = ''.join(before_parts)

    # Build the after line (with nested highlighting for added parts)
    after_parts = []
    for op, text in diffs:
        if op == 0:  # Equal
            after_parts.append(text)
        elif op == 1:  # Insertion (in after)
            after_parts.append(f'<span style="{ADDED_INNER_STYLE}">{text}</span>')
        # Skip deletions (op == -1) for the after line

    after_content = ''.join(after_parts)

    # Wrap content with placemarkers (inner HTML highlighting is preserved)
    before_html = f'{CHANGED_PLACEMARKER_OPEN}{before_content}{CHANGED_PLACEMARKER_CLOSED}'
    after_html = f'{CHANGED_INTO_PLACEMARKER_OPEN}{after_content}{CHANGED_INTO_PLACEMARKER_CLOSED}'

    return before_html, after_html, has_changes


def same_slicer(lst: List[str], start: int, end: int) -> List[str]:
    """Return a slice of the list, or a single element if start == end."""
    return lst[start:end] if start != end else [lst[start]]

# Export main public API
__all__ = [
    'render_diff',
    'customSequenceMatcher',
    'render_inline_word_diff',
    'render_nested_line_diff',
    'TOKENIZERS',
    'REMOVED_STYLE',
    'ADDED_STYLE',
    'REMOVED_INNER_STYLE',
    'ADDED_INNER_STYLE',
]
