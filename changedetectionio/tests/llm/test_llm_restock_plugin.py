"""
Tests for the LLM restock fallback plugin.

All LLM calls are mocked — no real API key required.
"""
import json
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _clear_llm_result_cache():
    """The plugin keeps a module-level result cache (keyed by model+prompt) so it won't
    re-bill the LLM when the meaningful page content is unchanged. That cache persists
    across tests in the same process, which makes token-accounting assertions order
    dependent (a cache hit returns zeroed tokens). Clear it before every test so each
    one exercises a fresh extraction."""
    from changedetectionio.processors.restock_diff.plugins import llm_restock
    llm_restock._LLM_RESULT_CACHE.clear()
    yield
    llm_restock._LLM_RESULT_CACHE.clear()


def _make_datastore(llm_model='gpt-4o-mini', enabled=True):
    """Minimal datastore mock with the fields the plugin reads."""
    ds = MagicMock()
    ds.data = {
        'settings': {
            'application': {
                'llm': {
                    'enabled': True,
                    'restock_use_fallback_extract': enabled,
                    'model': llm_model,
                    'api_key': 'test-key',
                    'api_base': '',
                    'tokens_total_cumulative': 0,
                    'tokens_this_month': 0,
                    'tokens_month_key': '2099-01',
                    'cost_usd_total_cumulative': 0.0,
                    'cost_usd_this_month': 0.0,
                },
            }
        }
    }
    return ds


