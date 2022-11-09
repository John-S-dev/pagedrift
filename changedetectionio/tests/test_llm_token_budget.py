#!/usr/bin/env python3
"""
Tests that verify global LLM token budget counters cannot be tampered with
via the API (watch PUT) or via form submissions (settings page POST).

This is critical for hosted deployments where the operator sets
LLM_TOKEN_BUDGET_MONTH in the container — tenants must not be able
to reset or inflate the counter themselves.
"""

import json
import os

import pytest
from flask import url_for

from changedetectionio.tests.util import live_server_setup, delete_all_watches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_token_counters(datastore, this_month=5000, total=12000):
    """Pre-load token counters into the datastore's llm settings dict."""
    from changedetectionio.llm.evaluator import _get_month_key
    app_settings = datastore.data['settings']['application']
    if 'llm' not in app_settings:
        app_settings['llm'] = {}
    app_settings['llm'].update({
        'model': 'gpt-4o-mini',
        'api_key': 'sk-test',
        'tokens_this_month': this_month,
        'tokens_total_cumulative': total,
        'tokens_month_key': _get_month_key(),
    })


