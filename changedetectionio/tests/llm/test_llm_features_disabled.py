"""
Smoke test for the LLM_FEATURES_DISABLED env var.

The env var is intended to hide every LLM/AI surface (settings tab, edit tab,
base-template AI toggle/modal) for hosted deployments. This test renders the
three primary pages with the env var set and verifies that none of the
LLM-related markers leak through.
"""
from flask import url_for


