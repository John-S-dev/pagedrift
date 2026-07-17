"""
Unit tests for changedetectionio/llm/response_parser.py

All functions are pure — no external dependencies needed.
"""

import pytest

class TestExtractJson:
    def test_plain_json_passes_through(self):
        raw = '{"important": true, "summary": "price dropped"}'
        assert _extract_json(raw) == raw

    def test_strips_json_code_fence(self):
        raw = '```json\n{"important": false, "summary": "no match"}\n```'
        result = _extract_json(raw)
        assert result.startswith('{')
        assert '"important"' in result

    def test_strips_plain_code_fence(self):
        raw = '```\n{"important": true, "summary": "ok"}\n```'
        result = _extract_json(raw)
        assert result.startswith('{')

    def test_extracts_json_from_surrounding_text(self):
        raw = 'Here is my response: {"important": true, "summary": "match"} — done.'
        result = _extract_json(raw)
        assert result == '{"important": true, "summary": "match"}'

    def test_multiline_json(self):
        raw = '{\n  "important": false,\n  "summary": "nothing relevant"\n}'
        result = _extract_json(raw)
        assert '"important"' in result

    def test_strips_reasoning_think_tags(self):
        raw = (
            '<think>\n'
            'Let us consider if {"important": false} is right. Actually, yes.\n'
            '</think>\n'
            '{"important": true, "summary": "Price fell to $300"}'
        )
        result = _extract_json(raw)
        assert result == '{"important": true, "summary": "Price fell to $300"}'

    def test_strips_reasoning_think_tags_with_code_fence(self):
        raw = (
            '<think>\nThinking about the price change.\n</think>\n'
            '```json\n{"important": false, "summary": "Cosmetic change only"}\n```'
        )
        result = _extract_json(raw)
        assert '"important"' in result
        assert '<think>' not in result


