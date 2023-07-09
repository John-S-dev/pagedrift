#!/usr/bin/env python3
"""
Simple unit tests for TimeExtension that mimic how safe_jinja.py uses it.
These tests demonstrate that the environment.default_timezone override works
exactly as intended in the actual application code.
"""

import arrow
from jinja2.sandbox import ImmutableSandboxedEnvironment
from changedetectionio.jinja2_custom.extensions.TimeExtension import TimeExtension


def test_default_timezone_override_like_safe_jinja(mocker):
    """
    Test that mirrors exactly how safe_jinja.py uses the TimeExtension.
    This is the simplest demonstration that environment.default_timezone works.
    """
    # Create environment (TimeExtension.__init__ sets default_timezone='UTC')
    jinja2_env = ImmutableSandboxedEnvironment(extensions=[TimeExtension])

    # Override the default timezone - exactly like safe_jinja.py does
    jinja2_env.default_timezone = 'America/New_York'

    # Mock arrow.now to return a fixed time
    fixed_time = arrow.Arrow(2025, 1, 15, 12, 0, 0, tzinfo='America/New_York')
    mock = mocker.patch("arrow.now", return_value=fixed_time)

    # Use empty string timezone - should use the overridden default
    template_str = "{% now '' %}"
    output = jinja2_env.from_string(template_str).render()

    # Verify arrow.now was called with the overridden timezone
    mock.assert_called_with('America/New_York')
    assert '2025' in output
    assert 'Jan' in output


def test_default_timezone_not_overridden(mocker):
    """
    Test that without override, the default 'UTC' from __init__ is used.
    """
    # Create environment (TimeExtension.__init__ sets default_timezone='UTC')
    jinja2_env = ImmutableSandboxedEnvironment(extensions=[TimeExtension])

    # DON'T override - should use 'UTC' default

    # Mock arrow.now
    fixed_time = arrow.Arrow(2025, 1, 15, 17, 0, 0, tzinfo='UTC')
    mock = mocker.patch("arrow.now", return_value=fixed_time)

    # Use empty string timezone - should use 'UTC' default
    template_str = "{% now '' %}"
    output = jinja2_env.from_string(template_str).render()

    # Verify arrow.now was called with 'UTC'
    mock.assert_called_with('UTC')
    assert '2025' in output


