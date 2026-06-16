"""
Tests for the LLM restock fallback plugin.

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


