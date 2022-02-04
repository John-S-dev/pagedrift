#!/usr/bin/env python3
"""
Security tests: LLM API key must never appear in any API response.

The LLM API key is a secret credential stored in
datastore.data['settings']['application']['llm']['api_key'].
It must never be leaked through any API endpoint — watch GET/list,
tag GET/list, system-info, notifications — even when the calling client
has a valid API token (which is a different kind of credential).

from flask import url_for

from changedetectionio.tests.util import live_server_setup, delete_all_watches

CANARY_KEY = 'sk-CANARY-SECRET-DO-NOT-EXPOSE-12345'


