#!/usr/bin/env python3

# run from dir above changedetectionio/ dir
# python3 -m unittest changedetectionio.tests.unit.test_llm_settings

import unittest

from pydantic import ValidationError

from changedetectionio.model.LLMSettings import (
    LLMSettings,
    LLM_DEFAULT_BUDGET_ACTION,
    LLM_DEFAULT_LOCAL_TOKEN_MULTIPLIER,
    LLM_DEFAULT_MAX_INPUT_CHARS,
    LLM_DEFAULT_MAX_SUMMARY_TOKENS,
    LLM_DEFAULT_THINKING_BUDGET,
)


class TestLLMSettingsDefaults(unittest.TestCase):
    def test_empty_dict_yields_default_model(self):
        s = LLMSettings.model_validate({})
        self.assertTrue(s.enabled)
        self.assertFalse(s.debug)
        self.assertEqual(s.model, '')
        self.assertEqual(s.api_key, '')
        self.assertEqual(s.thinking_budget, LLM_DEFAULT_THINKING_BUDGET)
        self.assertEqual(s.max_summary_tokens, LLM_DEFAULT_MAX_SUMMARY_TOKENS)
        self.assertEqual(s.local_token_multiplier, LLM_DEFAULT_LOCAL_TOKEN_MULTIPLIER)
        self.assertEqual(s.max_input_chars, LLM_DEFAULT_MAX_INPUT_CHARS)
        self.assertEqual(s.budget_action, LLM_DEFAULT_BUDGET_ACTION)
        self.assertEqual(s.tokens_total_cumulative, 0)
        self.assertEqual(s.cost_usd_this_month, 0.0)

    def test_default_construct_matches_validate_empty(self):
        self.assertEqual(LLMSettings().model_dump(), LLMSettings.model_validate({}).model_dump())


class TestLLMSettingsValidation(unittest.TestCase):
    def test_stripped_keys_validate(self):
        s = LLMSettings.model_validate({'model': 'gpt-4o-mini', 'enabled': False})
        self.assertEqual(s.model, 'gpt-4o-mini')
        self.assertFalse(s.enabled)


