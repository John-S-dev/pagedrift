import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from changedetectionio.browser_steps.browser_steps import browsersteps_live_ui
from changedetectionio.content_fetchers.base import get_playwright_bypass_csp


def test_playwright_bypass_csp_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv('PLAYWRIGHT_BYPASS_CSP', raising=False)

    assert get_playwright_bypass_csp() is True


@pytest.mark.parametrize(
    ('configured_value', 'expected'),
    [
        ('true', True),
        ('1', True),
        ('yes', True),
        ('false', False),
        ('0', False),
        ('no', False),
    ],
)
def test_playwright_bypass_csp_parses_boolean_environment_values(
    monkeypatch, configured_value, expected
):
    monkeypatch.setenv('PLAYWRIGHT_BYPASS_CSP', configured_value)

    assert get_playwright_bypass_csp() is expected


