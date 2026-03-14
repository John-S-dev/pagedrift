from flask import Blueprint, request, url_for, flash, render_template, redirect
from flask_babel import gettext
import time
from loguru import logger

from changedetectionio.store import ChangeDetectionStore
from changedetectionio.auth_decorator import login_optionally_required
from changedetectionio import html_tools

def construct_blueprint(datastore: ChangeDetectionStore):
    preview_blueprint = Blueprint('ui_preview', __name__, template_folder="../ui/templates")


    @preview_blueprint.route("/preview/<uuid_str:uuid>", methods=['GET', 'POST'])
    @login_optionally_required
    def preview_page(uuid):
        """
        Render the preview page for a watch.

        This route is processor-aware: it delegates rendering to the processor's
        preview.py module, allowing different processor types to provide
        custom visualizations:
        - text_json_diff: Text preview with syntax highlighting
        - image_ssim_diff: Image preview with proper rendering
        - restock_diff: Could show latest price/stock data

        Each processor implements processors/{type}/preview.py::render()
        If a processor doesn't have a preview module, falls back to default text preview.
        """

        if uuid == 'first':
            uuid = list(datastore.data['watching'].keys()).pop()
        try:
            watch = datastore.data['watching'][uuid]
        except KeyError:
            flash(gettext("No history found for the specified link, bad link?"), "error")
            return redirect(url_for('watchlist.index'))

        # Get the processor type for this watch
        processor_name = watch.get('processor', 'text_json_diff')

        # Try to get the processor's preview module (works for both built-in and plugin processors)
        from changedetectionio.processors import get_processor_submodule
        processor_module = get_processor_submodule(processor_name, 'preview')

        # Call the processor's render() function
        if processor_module and hasattr(processor_module, 'render'):
            return processor_module.render(
                watch=watch,
                datastore=datastore,
                request=request,
                url_for=url_for,
                render_template=render_template,
                flash=flash,
                redirect=redirect
            )

