"""
Thin wrapper around litellm.completion.
Keeps litellm import isolated so the rest of the codebase doesn't depend on it directly,
and makes the call easy to mock in tests.
"""

import logging
import os

from loguru import logger

# Default output token cap for JSON-returning calls (intent eval, preview, setup).
# These return small JSON objects — 400 is enough for a verbose explanation while
# still preventing runaway cost. Change summaries pass their own max_tokens via
# _summary_max_tokens() and are NOT subject to this cap.
_MAX_COMPLETION_TOKENS = 400

# Default request timeout (seconds). Raised from 60 to 300 because even cloud
# reasoning models can be slow on the first hit (issue #4225). Overridable via
# LLM_TIMEOUT.
DEFAULT_TIMEOUT = int(os.getenv('LLM_TIMEOUT', 300))
# Relaxed timeout for local / self-hosted endpoints (Ollama, vLLM, LM Studio,
# llama.cpp on localhost or a LAN address). These run on modest hardware and can
# spend many minutes on prompt prefill before the first token, so they get a much
# longer deadline (Hermes-style, 30 min). Overridable via LLM_LOCAL_TIMEOUT; see
# evaluator.resolve_llm_timeout() for how the endpoint is classified.
DEFAULT_LOCAL_TIMEOUT = int(os.getenv('LLM_LOCAL_TIMEOUT', 1800))
# Models and reasoning architectures that reject explicit sampling parameters (temperature/top_p)
_NO_TEMPERATURE_MODEL_KEYWORDS = ('flash-lite', 'thinking-exp', 'o1', 'o3', 'o4')

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


