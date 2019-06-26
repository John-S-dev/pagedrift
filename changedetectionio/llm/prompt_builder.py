"""
Prompt construction for LLM evaluation calls.
Pure functions — no side effects, fully testable.
"""

import re

from .bm25_trim import trim_to_relevant

_AGO_RE = re.compile(r'^\d+\s+\w+\s+ago$', re.IGNORECASE)

SNAPSHOT_CONTEXT_CHARS = 30_000  # current page state excerpt sent alongside the diff


def _annotate_moved_lines(diff_text: str) -> str:
    """
    Pre-process a unified diff to mark lines that appear on both the + and - sides
    as [MOVED] (~ prefix) rather than genuinely added/removed. This prevents the LLM from
    incorrectly classifying repositioned content as new or deleted.
    Also marks standalone relative timestamps (e.g. '3 hours ago') as ~ trivial.

    Lines are compared after stripping leading +/- and whitespace so that
    indentation changes don't prevent matching.
    """
    lines = diff_text.splitlines()
    added_texts = {
        line[1:].strip().lower() for line in lines if line.startswith('+') and line[1:].strip()
    }
    removed_texts = {
        line[1:].strip().lower() for line in lines if line.startswith('-') and line[1:].strip()
    }
    moved_texts = added_texts & removed_texts

    result = []
    has_changes = False
    for line in lines:
        if line.startswith(('+', '-')):
            bare = line[1:].strip().lower()
            if bare in moved_texts or _AGO_RE.match(line[1:].strip()):
                result.append(f'~{line[1:]}')  # ~ prefix = moved/reordered/trivial, skip
                has_changes = True
                continue
        result.append(line)
    return '\n'.join(result) if has_changes else diff_text


def build_eval_prompt(
    intent: str, diff: str, current_snapshot: str = '', url: str = '', title: str = ''
) -> str:
    """
    Build the user message for a diff evaluation call.
    The system prompt is kept separate (see build_eval_system_prompt).
    """
    parts = []

    if url:
        parts.append(f"URL: {url}")
    if title:
        parts.append(f"Page title: {title}")

    parts.append(f"Intent: {intent}")

    if current_snapshot:
        excerpt = trim_to_relevant(current_snapshot, intent, max_chars=SNAPSHOT_CONTEXT_CHARS)
        if excerpt:
            parts.append(f"\nCurrent page state (relevant excerpt):\n{excerpt}")

    parts.append(f"\nWhat changed (diff):\n{diff}")

    return '\n'.join(parts)


def build_eval_system_prompt() -> str:
    return (
        "You are a precise, reliable website-change evaluator for a monitoring tool.\n"
        "Your job is to read a unified diff and decide whether it matches a user's stated intent.\n"
        "Accuracy is critical — false positives waste the user's attention; false negatives miss what they care about.\n\n"
        "Diff format:\n"
        "- Lines starting with '+' are newly ADDED content\n"
        "- Lines starting with '-' are REMOVED content\n"
        "- Lines starting with ' ' (space) are unchanged context\n\n"
        "Respond with ONLY a JSON object — no markdown, no explanation outside it:\n"
        '{"important": true/false, "summary": "one sentence describing the relevant change, or why it doesn\'t match"}\n\n'
        "Rules:\n"
        "- important=true ONLY when the diff clearly and specifically matches the intent — be strict\n"
        "- Pay close attention to direction: an intent about price drops means removed (-) prices and added (+) lower prices\n"
        "- The user's intent always wins. If the intent explicitly asks about timestamps, numbers, counters, "
        "thresholds, or any specific value (e.g. 'when the timestamp is greater than 1778599592', "
        "'when stock count > 5'), evaluate the diff against that intent — do NOT dismiss it as cosmetic.\n"
        "- Otherwise: empty, trivial, or genuinely cosmetic diffs (heartbeat timestamps, view counters, "
        "whitespace, navigation tweaks) default to important=false\n"
        "- For numeric comparisons in the intent, parse the values explicitly and compare them — "
        "do not eyeball or round\n"
        "- If the same text appears in both removed (-) and added (+) lines the content has likely just "
        "shifted or been reordered. Treat pure reordering as important=false unless the intent "
        "explicitly asks about order or position.\n"
        "- Use OR logic when the intent lists multiple triggers — any one matching is sufficient\n"
        "- When uncertain whether a change truly matches, prefer important=false and explain why in the summary\n"
        "- Summary must be in the same language as the intent\n"
        "- If important=false, the summary must clearly explain what changed and why it does not match"
    )


def build_preview_prompt(intent: str, content: str, url: str = '', title: str = '') -> str:
    """
    Build the user message for a live-preview extraction call.
    Unlike build_eval_prompt (which analyses a diff), this asks the LLM to
    extract relevant information from the *current* page content — giving the
    user a direct answer to their intent so they can verify it makes sense
    before saving.
    """
    parts = []
    if url:
        parts.append(f"URL: {url}")
    if title:
        parts.append(f"Page title: {title}")
    parts.append(f"Intent / question: {intent}")
    parts.append(f"\nPage content:\n{content[:6_000]}")
    return '\n'.join(parts)


def build_preview_system_prompt() -> str:
    return (
        "You are a precise, detail-oriented web page content analyst for a website monitoring tool.\n"
        "Given the user's intent or question and the current page content, extract and directly answer "
        "what the intent is looking for. Never guess or paraphrase — report only what the page actually contains.\n\n"
        "Respond with ONLY a JSON object — no markdown, no explanation outside it:\n"
        '{"found": true/false, "answer": "concise direct answer or extraction"}\n\n'
        "Rules:\n"
        "- found=true when the page clearly contains something relevant to the intent\n"
        "- answer must directly address the intent with specific values where possible "
        "(e.g. for 'current price?' → '$149.99', not 'a price is shown')\n"
        "- answer must be in the same language as the intent\n"
        "- Keep answer brief — one or two sentences maximum\n"
        "- If found=false, briefly state what the page contains instead"
    )


