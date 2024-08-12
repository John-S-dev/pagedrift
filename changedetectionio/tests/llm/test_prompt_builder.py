"""
Unit tests for changedetectionio/llm/prompt_builder.py

All functions are pure — no external dependencies needed.
"""

from changedetectionio.llm.prompt_builder import (
    _annotate_moved_lines,
    build_eval_prompt,
    build_eval_system_prompt,
    build_setup_prompt,
    build_setup_system_prompt,
)


class TestAnnotateMovedLines:
    def test_annotate_moved_lines_marks_reordered_content(self):
        diff = "- Item Alpha\n+ Item Beta\n+ Item Alpha\n- Item Beta"
        annotated = _annotate_moved_lines(diff)
        assert "~ Item Alpha" in annotated
        assert "~ Item Beta" in annotated

    def test_annotate_standalone_timestamp_without_moved_lines(self):
        # Even when there are NO moved lines, standalone relative timestamps must be annotated
        diff = "- 2 hours ago\n+ 3 hours ago\n+ Genuine new article headline"
        annotated = _annotate_moved_lines(diff)
        assert "~ 2 hours ago" in annotated
        assert "~ 3 hours ago" in annotated
        assert "+ Genuine new article headline" in annotated

    def test_unrelated_diff_remains_unchanged(self):
        diff = "- Old price: $100\n+ New price: $80"
        annotated = _annotate_moved_lines(diff)
        assert annotated == diff


class TestBuildSetupPrompt:
    def test_contains_intent(self):
        prompt = build_setup_prompt(
            intent='monitor footer changes',
            snapshot_text='<footer>Copyright 2024</footer>',
        )
        assert 'monitor footer changes' in prompt

    def test_contains_url_when_provided(self):
        prompt = build_setup_prompt(
            intent='price',
            snapshot_text='price: $10',
            url='https://shop.example.com',
        )
        assert 'https://shop.example.com' in prompt

    def test_url_absent_when_not_provided(self):
        prompt = build_setup_prompt(intent='price', snapshot_text='text')
        assert 'URL:' not in prompt

    def test_large_snapshot_trimmed(self):
        big_snapshot = 'unrelated junk line\n' * 500
        prompt = build_setup_prompt(
            intent='monitor price section',
            snapshot_text=big_snapshot,
        )
        assert len(prompt) < len(big_snapshot)


class TestBuildSetupSystemPrompt:
    def test_returns_string(self):
        result = build_setup_system_prompt()
        assert isinstance(result, str)

    def test_forbids_positional_selectors(self):
        result = build_setup_system_prompt()
        assert 'nth-child' in result or 'positional' in result

    def test_defines_needs_prefilter_field(self):
        result = build_setup_system_prompt()
        assert 'needs_prefilter' in result

    def test_defines_selector_field(self):
        result = build_setup_system_prompt()
        assert 'selector' in result
