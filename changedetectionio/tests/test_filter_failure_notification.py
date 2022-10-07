import os
import time
from flask import url_for
from .util import set_original_response, wait_for_all_checks, wait_for_notification_endpoint_output, delete_all_watches
from ..notification import valid_notification_formats


def test_check_include_filters_failure_notification(client, live_server, measure_memory_usage, datastore_path):
    #   #  live_server_setup(live_server) # Setup on conftest per function
    run_filter_test(client=client, live_server=live_server, content_filter='#nope-doesnt-exist', app_notification_format=valid_notification_formats.get('htmlcolor'), datastore_path=datastore_path)
    # Check markup send conversion didnt affect plaintext preference
    run_filter_test(client=client, live_server=live_server, content_filter='#nope-doesnt-exist', app_notification_format=valid_notification_formats.get('text'), datastore_path=datastore_path)
    delete_all_watches(client)

