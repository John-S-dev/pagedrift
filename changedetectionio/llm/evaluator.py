"""
LLM evaluation orchestration.

Two public entry points:
  - run_setup(watch, datastore)        — one-time: decide if pre-filter needed
  - evaluate_change(watch, datastore, diff, current_snapshot) — per-change evaluation

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from loguru import logger

from changedetectionio.strtobool import strtobool

from . import client as llm_client
from .prompt_builder import (
    build_change_summary_prompt, build_change_summary_system_prompt,
    build_eval_prompt, build_eval_system_prompt,
    build_preview_prompt, build_preview_system_prompt,
    build_setup_prompt, build_setup_system_prompt,
)
from .response_parser import parse_eval_response, parse_preview_response, parse_setup_response

# Default prompt used when the user hasn't configured llm_change_summary.
# This owns the OUTPUT FORMAT (structure, sections, style, language). The system prompt
# in prompt_builder.build_change_summary_system_prompt() only covers how to READ the diff.
# Users can replace this entirely (e.g. "Just tell me the new timestamp.") without
# fighting hard-coded structure rules from the system prompt.
DEFAULT_CHANGE_SUMMARY_PROMPT = (
    "Describe what changed in plain English using these sections, in this fixed order — "
    "omit a section entirely if there is nothing to report for it:\n"
    "  Added: ...\n"
    "  Changed: ...\n"
    "  Removed: ...\n"
    "The Removed section MUST always be last. Never place removals before additions or changes.\n\n"
    "List items as bullet points with key details for each one. Be considerate of the style "
    "of content you are summarising and adjust your report accordingly.\n"
    "Do not list standalone timestamps like '3 hours ago', 'Yesterday', '2 minutes ago' as added "
    "or removed items — they are not meaningful content changes.\n"
    "For content-heavy pages (news, listings, feeds): quote or paraphrase the specific new "
    "headlines, items, or entries that were added — do not collapse them into vague phrases "
    "like 'new articles were added' or 'section was expanded'.\n"
    "For large blocks of new text (full articles, documents, long paragraphs): briefly summarise "
    "the substance in 1-2 sentences capturing the key point — do not just repeat the title.\n\n"
    "Do not quote non-English text verbatim; translate and summarise all content into English. "
    "Do not give partial listings such as 'Examples include:', always be thorough."
)

# How a watch's or tag's llm_change_summary combines with the prompt it inherits.
# 'replace' is the default and the historical behaviour; 'append' lets a watch add a line
# or two to the inherited prompt instead of holding a full private copy of it, so later
# edits to the global prompt still reach that watch. Re #4251.
LLM_PROMPT_MODE_REPLACE = 'replace'
LLM_PROMPT_MODE_APPEND = 'append'


def _summary_max_tokens(diff: str, max_cap: int = LLM_DEFAULT_MAX_SUMMARY_TOKENS) -> int:
    """Scale completion tokens to diff size: floor 400, ~1 token per 4 chars, ceiling max_cap."""
    return max(400, min(len(diff) // 4, max_cap))


