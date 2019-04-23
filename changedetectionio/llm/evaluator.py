"""
LLM evaluation orchestration.

Two public entry points:
  - run_setup(watch, datastore)        — one-time: decide if pre-filter needed
  - evaluate_change(watch, datastore, diff, current_snapshot) — per-change evaluation

Intent resolution: watch.llm_intent → first tag with llm_intent whose AI switch is "on"
                   (see tag_llm_applies_to_watches) → None (no evaluation)
Cache: each (intent, diff) pair is evaluated exactly once, result stored in watch.

Environment variable overrides (take priority over datastore settings):
  LLM_MODEL    — model string (e.g. "gpt-4o-mini", "ollama/llama3.2")
  LLM_API_KEY  — API key for cloud providers
  LLM_API_BASE — base URL for local/custom endpoints (e.g. http://localhost:11434)
  LLM_TIMEOUT       — per-request timeout in seconds (default 300). When set, it
                      applies to every endpoint (a single hard ceiling).
  LLM_LOCAL_TIMEOUT — timeout in seconds for local/self-hosted endpoints (api_base
                      on a private/LAN address); default 1800. Applied automatically
                      unless LLM_TIMEOUT is set. See resolve_llm_timeout().
"""

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

from changedetectionio.model.LLMSettings import (
    LLMSettings,
    LLM_DEFAULT_MAX_INPUT_CHARS as _DEFAULT_MAX_INPUT_CHARS,
    LLM_DEFAULT_MAX_SUMMARY_TOKENS,
    LLM_DEFAULT_THINKING_BUDGET,
)


def is_llm_features_disabled() -> bool:
    """True when the LLM_FEATURES_DISABLED env var is set to a truthy value."""
    return bool(strtobool(os.getenv('LLM_FEATURES_DISABLED', '')))


def get_llm_settings(datastore) -> LLMSettings:
    """Hydrate the LLM config dict at settings.application.llm into a validated model.

    Returns a default-constructed LLMSettings when the dict is missing or empty —
    callers never have to None-check the result. The storage layer remains a plain
    dict; this is only the validation/typing layer for reads.
    """
    cfg = datastore.data.get('settings', {}).get('application', {}).get('llm') or {}
    return LLMSettings.model_validate(cfg)


def _get_max_input_chars(datastore) -> int:
    """Max input characters to send to the LLM. Resolution: env var → datastore → 100,000.
    Always returns at least 1 — unlimited is not permitted.
    """
    env_val = os.getenv('LLM_MAX_INPUT_CHARS', '').strip()
    if env_val.isdigit() and int(env_val) > 0:
        return int(env_val)
    stored = get_llm_settings(datastore).max_input_chars
    if stored and stored > 0:
        return stored
    return _DEFAULT_MAX_INPUT_CHARS


class LLMInputTooLargeError(Exception):
    pass


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


def _tags_applying_llm(watch, datastore):
    """Yield this watch's groups, in order, that hand their AI settings to their watches."""
    for tag in _watch_tags(watch, datastore):
        if tag_llm_applies_to_watches(tag):
            yield tag


def llm_enabled_for_watch(watch, datastore) -> tuple[bool, str]:
    """Is automatic AI evaluation switched on for this watch? Returns (enabled, source).

    See #4204 — users with hundreds of watches want AI on only a select few.

    A group with an opinion decides for all of its watches ("the group setting overrides any
    watch on/off"), so the first such group wins over the watch's own switch; groups set to
    "leave it to each watch" are skipped. With no group deciding, the watch decides — and a
    missing key means on, so watches predating this switch keep working.

    Only gates *automatic* spend (the worker's intent/summary passes and the restock AI
    plugin). Explicit user actions — the diff page "Summary" button, the intent preview —
    stay available, since those cost tokens only when someone deliberately clicks.
    """
    for tag in _watch_tags(watch, datastore):
        decision = tag_llm_decision(tag)
        if decision is not None:
            return decision, tag.get('title', 'tag')
    return bool(watch.get('llm_backend_profile', True)), 'watch'


def resolve_llm_field(watch, datastore, field: str) -> tuple[str, str]:
    """
    Generic cascade resolver for any LLM per-watch field.
    Returns (value, source) where source is 'watch' or tag title.
    Returns ('', '') if not set anywhere.
    """
    value = (watch.get(field) or '').strip()
    if value:
        return value, 'watch'

    for tag in _tags_applying_llm(watch, datastore):
        tag_value = (tag.get(field) or '').strip()
        if tag_value:
            return tag_value, tag.get('title', 'tag')

    return '', ''


