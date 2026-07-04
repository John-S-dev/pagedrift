import json
import logging
import os
import re

from flask import Blueprint, jsonify, redirect, url_for, flash
from flask_babel import gettext
from loguru import logger

from changedetectionio.store import ChangeDetectionStore
from changedetectionio.auth_decorator import login_optionally_required


class _LiteLLMWarningCapture(logging.Handler):
    """Capture warnings emitted on the 'LiteLLM' stdlib logger during a single call.

    litellm.get_valid_models() catches HTTP/auth errors internally, logs a warning,
    and returns []. Without capturing that warning we can't tell the user *why*
    no models came back (bad key vs. offline vs. genuinely empty model list).
    """
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        try:
            self.messages.append(record.getMessage())
        except Exception:
            pass


def _humanize_litellm_error(raw: str) -> str:
    # litellm warnings typically look like:
    #   "Error getting valid models: Failed to get models: { 'error': { 'message': '...' } }"
    # Pull the inner provider message when present; otherwise trim the boilerplate.
    if not raw:
        return raw
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            body = json.loads(m.group(0))
            inner = (body.get('error') or {}).get('message') or body.get('message')
            if inner:
                return inner
        except Exception:
            pass
    cleaned = re.sub(r'^Error getting valid models:\s*', '', raw)
    cleaned = re.sub(r'^Failed to get models:\s*', '', cleaned).strip()
    return cleaned[:500]


def construct_llm_blueprint(datastore: ChangeDetectionStore):
    llm_blueprint = Blueprint('llm', __name__)

    @llm_blueprint.route("/models", methods=['GET'])
    @login_optionally_required
    def llm_get_models():
        from flask import request
        from changedetectionio.validate_url import is_llm_api_base_safe
        provider = request.args.get('provider', '').strip()
        api_key  = request.args.get('api_key',  '').strip()
        api_base = request.args.get('api_base', '').strip()

        logger.debug(f"LLM model list requested for provider={provider!r} api_base={api_base!r}")

        if not provider:
            logger.debug("LLM model list: no provider specified, returning 400")
            return jsonify({'models': [], 'error': 'No provider specified'}), 400

        ok, reason = is_llm_api_base_safe(api_base)
        if not ok:
            logger.warning(f"LLM model list refused: api_base failed SSRF check ({reason})")
            return jsonify({'models': [], 'error': reason}), 400

        # Credential-exfiltration guard (GHSA-g36r-fm2p-87xm).
        # Only substitute the stored api_key when api_base matches the stored
        # api_base. If the caller pointed at a different destination, refuse —
        # otherwise a CSRF / unauthenticated request can ship the operator's
        # long-lived provider key (sent as Authorization: Bearer …) to an
        # attacker-controlled URL.
        stored_llm     = datastore.data['settings']['application'].get('llm') or {}
        stored_api_base = (stored_llm.get('api_base') or '').strip()
        if not api_key:
            if api_base == stored_api_base:
                api_key = (stored_llm.get('api_key') or '')
                logger.debug("LLM model list: no api_key in request, using stored key (api_base matches saved)")
            elif api_base:
                logger.warning("LLM model list refused: api_base differs from saved config but no api_key supplied")
                return jsonify({'models': [], 'error': gettext(
                    "api_key is required when api_base differs from the saved configuration. "
                    "Refusing to send the stored API key to a different endpoint."
                )}), 400

        _PREFIXES = {'gemini': 'gemini/', 'ollama': 'ollama/', 'openrouter': 'openrouter/',
                     'openai_compatible': 'openai/'}
        # vLLM / LM Studio / llama.cpp speak OpenAI's wire format — route through litellm's
        # 'openai' provider but keep the UI-level name distinct from cloud OpenAI.
        _LITELLM_PROVIDER = {'openai_compatible': 'openai'}
        prefix = _PREFIXES.get(provider, '')
        litellm_provider = _LITELLM_PROVIDER.get(provider, provider)

        try:
            import litellm
            logger.debug(f"LLM model list: calling litellm.get_valid_models provider={provider!r} (litellm={litellm_provider!r}) api_base={api_base!r}")

            capture = _LiteLLMWarningCapture()
            litellm_logger = logging.getLogger('LiteLLM')
            litellm_logger.addHandler(capture)
            try:
                raw = litellm.get_valid_models(
                    check_provider_endpoint=True,
                    custom_llm_provider=litellm_provider,
                    api_key=api_key or None,
                    api_base=api_base or None,
                ) or []
            finally:
                litellm_logger.removeHandler(capture)

            models = sorted({(m if m.startswith(prefix) else prefix + m) for m in raw})

