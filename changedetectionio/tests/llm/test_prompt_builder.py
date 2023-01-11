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


