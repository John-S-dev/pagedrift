"""
Base contract + shared helpers for a processor's history/diff ("difference") page.

Each processor can provide a custom history/diff view by shipping a
``processors/<name>/difference.py`` module that exposes a module-level ``render(...)``
function. The route ``blueprint/ui/diff.py::diff_history_page`` resolves it via
``get_processor_submodule(processor_name, 'difference')`` and calls ``render(...)`` with the
keyword contract below; processors without one fall back to ``text_json_diff``.

