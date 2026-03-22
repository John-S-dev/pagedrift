"""
Diff rendering module for change detection.

from .tokenizers import TOKENIZERS, tokenize_words_and_html

# Remember! gmail, outlook etc dont support <style> must be inline.
# Gmail: strips <ins> and <del> tags entirely.
# This is for the WHOLE line background style
REMOVED_STYLE = "background-color: #fadad7; color: #b30000;"
ADDED_STYLE = "background-color: #eaf2c2; color: #406619;"
HTML_REMOVED_STYLE = REMOVED_STYLE  # Export alias for handler.py
HTML_ADDED_STYLE = ADDED_STYLE      # Export alias for handler.py

CHANGED_PLACEMARKER_OPEN = '@changed_PLACEMARKER_OPEN'
CHANGED_PLACEMARKER_CLOSED = '@changed_PLACEMARKER_CLOSED'

CHANGED_INTO_PLACEMARKER_OPEN = '@changed_into_PLACEMARKER_OPEN'
CHANGED_INTO_PLACEMARKER_CLOSED = '@changed_into_PLACEMARKER_CLOSED'

