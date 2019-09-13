"""
Thin wrapper around litellm.completion.
Keeps litellm import isolated so the rest of the codebase doesn't depend on it directly,
and makes the call easy to mock in tests.
"""

import logging
import os

from loguru import logger

DEFAULT_RETRIES = 3


class _LoguruInterceptHandler(logging.Handler):
    # Routes litellm's stdlib log records through loguru so debug output
    # uses the same format/sink as the rest of the app.
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except (ValueError, AttributeError):
            level = record.levelno
        logger.opt(exception=record.exc_info).log(level, record.getMessage())


_debug_installed = False


def _install_litellm_debug():
    # Attach our loguru intercept and clear any pre-existing handlers so litellm's
    # own stdout StreamHandler (installed by _turn_on_debug / set_verbose) doesn't
    # double-emit. Setting the logger level to DEBUG is enough to make litellm
    # produce debug records — we don't call _turn_on_debug() for that reason.
    global _debug_installed
    if _debug_installed:
        return

    handler = _LoguruInterceptHandler()
    handler.setLevel(logging.DEBUG)
    for _name in ('LiteLLM', 'litellm', 'litellm.utils', 'litellm.router'):
        _lg = logging.getLogger(_name)
        _lg.handlers = []
        _lg.setLevel(logging.DEBUG)
        _lg.addHandler(handler)
        _lg.propagate = False

    _debug_installed = True
    logger.info("LLM client: litellm debug logging routed through loguru")


