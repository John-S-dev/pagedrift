"""
Base data extraction module for all processors.

This module handles extracting data from watch history using regex patterns
and exporting to CSV format. This is the default extractor that all processors
(text_json_diff, restock_diff, etc.) can use by default or override.
"""

import os
from flask_babel import gettext
from loguru import logger


def render_form(watch, datastore, request, url_for, render_template, flash, redirect, extract_form=None):
    """
    Render the data extraction form.

    Args:
        watch: The watch object
        datastore: The ChangeDetectionStore instance
        request: Flask request object
        url_for: Flask url_for function
        render_template: Flask render_template function
        flash: Flask flash function
        redirect: Flask redirect function
        extract_form: Optional pre-built extract form (for error cases)

    Returns:
        Rendered HTML response with the extraction form
    """
    from changedetectionio import forms

    uuid = watch.get('uuid')

    # Use provided form or create a new one
    if extract_form is None:
        extract_form = forms.extractDataForm(
            formdata=request.form,
            data={'extract_regex': request.form.get('extract_regex', '')}
        )

    # Get error information for the template
    screenshot_url = watch.get_screenshot()

    is_html_webdriver = watch.fetcher_supports_screenshots

    password_enabled_and_share_is_off = False
    if datastore.data['settings']['application'].get('password') or os.getenv("SALTED_PASS", False):
        password_enabled_and_share_is_off = not datastore.data['settings']['application'].get('shared_diff_access')

    # Use the shared default template from processors/templates/
    # Processors can override this by creating their own extract.py with custom template logic
    output = render_template(
        "extract.html",
        uuid=uuid,
        extract_form=extract_form,
        watch_a=watch,
        last_error=watch['last_error'],
        last_error_screenshot=watch.get_error_snapshot(),
        last_error_text=watch.get_error_text(),
        screenshot=screenshot_url,
        is_html_webdriver=is_html_webdriver,
        password_enabled_and_share_is_off=password_enabled_and_share_is_off,
        extra_title=f" - {watch.label} - {gettext('Extract Data')}",
        extra_stylesheets=[url_for('static_content', group='styles', filename='diff.css')],
        pure_menu_fixed=False
    )

    return output


