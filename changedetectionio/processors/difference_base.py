"""
Base contract + shared helpers for a processor's history/diff ("difference") page.

Each processor can provide a custom history/diff view by shipping a
``processors/<name>/difference.py`` module that exposes a module-level ``render(...)``
function. The route ``blueprint/ui/diff.py::diff_history_page`` resolves it via
``get_processor_submodule(processor_name, 'difference')`` and calls ``render(...)`` with the
keyword contract below; processors without one fall back to ``text_json_diff``.

This module formalises that previously-implicit contract:
  * ``DifferenceRenderer`` documents the ``render(...)`` signature (for typing/static checks).
  * ``resolve_diff_versions()`` centralises the from/to version selection that was duplicated
    between ``text_json_diff/difference.py`` and the ``/diff/.../llm-summary`` route, so every
    processor resolves "which two snapshots am I comparing" identically.
"""
from dataclasses import dataclass
from typing import Any, List, Protocol, runtime_checkable

from loguru import logger


@runtime_checkable
class DifferenceRenderer(Protocol):
    """The contract a processor's ``difference.py`` module must satisfy.

    Implemented as a module-level function (not a class method), so a conforming module looks
    like::

        def render(watch, datastore, request, url_for, render_template, flash, redirect,
                   extract_form=None):
            ...
            return render_template(...)   # a Flask response

    Returns a Flask response (rendered template / redirect / make_response).
    """

    def render(self, watch, datastore, request, url_for, render_template, flash, redirect,
               extract_form: Any = None) -> Any:
        ...


