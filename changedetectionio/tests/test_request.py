import json
import os
import time
from flask import url_for
from . util import set_original_response, set_modified_response, live_server_setup, wait_for_all_checks, extract_UUID_from_client, delete_all_watches



# Hard to just add more live server URLs when one test is already running (I think)
# So we add our test here (was in a different file)
def test_headers_in_request(client, live_server, measure_memory_usage, datastore_path):
    #ve_server_setup(live_server)
    # Add our URL to the import page
    test_url = url_for('test_headers', _external=True)
    if os.getenv('PLAYWRIGHT_DRIVER_URL'):
        # Because its no longer calling back to localhost but from the browser container, set in test-only.yml
        test_url = test_url.replace('localhost', 'changedet')

    # Add the test URL twice, we will check
    uuidA = client.application.config.get('DATASTORE').add_watch(url=test_url)
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)

    wait_for_all_checks(client)

    uuidB = client.application.config.get('DATASTORE').add_watch(url=test_url)
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)

    wait_for_all_checks(client)
    cookie_header = '_ga=GA1.2.1022228332; cookie-preferences=analytics:accepted;'


    # Add some headers to a request
    res = client.post(
        url_for("ui.ui_edit.edit_page", uuid=uuidA),
        data={
              "url": test_url,
              "tags": "",
              "fetch_backend": 'html_webdriver' if os.getenv('PLAYWRIGHT_DRIVER_URL') else 'html_requests',
              "headers": "jinja2:{{ 1+1 }}\nxxx:ooo\ncool:yeah\r\ncookie:"+cookie_header,
              "time_between_check_use_default": "y"},
        follow_redirects=True
    )
    assert b"Updated watch." in res.data

    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)

    # Give the thread time to pick up the first version
    wait_for_all_checks(client)

    # The service should echo back the request headers
    res = client.get(
        url_for("ui.ui_preview.preview_page", uuid=uuidA),
        follow_redirects=True
    )

    # Flask will convert the header key to uppercase
    assert b"Jinja2:2" in res.data
    assert b"Xxx:ooo" in res.data
    assert b"Cool:yeah" in res.data

    # The test call service will return the headers as the body
    from html import escape
    assert escape(cookie_header).encode('utf-8') in res.data

    wait_for_all_checks(client)

    # Re #137 -  It should have only one set of headers entered
    watches_with_headers = 0
    for k, watch in client.application.config.get('DATASTORE').data.get('watching').items():
            if (len(watch['headers'])):
                watches_with_headers += 1
    assert watches_with_headers == 1

    # 'server' http header was automatically recorded
    for k, watch in client.application.config.get('DATASTORE').data.get('watching').items():
        assert 'custom' in watch.get('remote_server_reply') # added in util.py

    delete_all_watches(client)

    wait_for_all_checks(client)

    watches_with_method = 0

    # Read individual watch.json files
    for uuid in client.application.config.get('DATASTORE').data['watching'].keys():
        watch_json_file = os.path.join(datastore_path, uuid, 'watch.json')
        assert os.path.exists(watch_json_file), f"watch.json should exist at {watch_json_file}"
        with open(watch_json_file, 'r', encoding='utf-8') as f:
            watch_data = json.load(f)
            if watch_data.get('method') == 'PATCH':
                watches_with_method += 1

    # Should be only one with method set to PATCH
    assert watches_with_method == 1

    delete_all_watches(client)

