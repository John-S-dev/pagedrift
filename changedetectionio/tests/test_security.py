import io
import os
import re
import time
import pytest

from flask import url_for
from zipfile import ZipFile, ZIP_DEFLATED

from changedetectionio.tests.util import set_modified_response
from .util import live_server_setup, wait_for_all_checks, delete_all_watches
from .. import strtobool


def set_original_response(datastore_path):
    test_return_data = """<html>
    <head><title>head title</title></head>
    <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
     <span class="foobar-detection" style='display:none'></span>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None


def test_favicon_inline_data_uri(client, live_server, measure_memory_usage, datastore_path):
    """
    bump_favicon() must handle a data URI as the url parameter.
    Previously this logged "Cant work out file extension from 'data:image/png;base64,...'" and bailed.
    The mime_type from the data URI should be used to pick the correct extension.
    """
    import base64
    import os

    # 1x1 transparent PNG (minimal valid PNG bytes)
    PNG_BYTES = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
        b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    png_b64 = base64.b64encode(PNG_BYTES).decode()
    data_uri = f"data:image/png;base64,{png_b64}"

    uuid = client.application.config.get('DATASTORE').add_watch(url='https://localhost')
    watch = live_server.app.config['DATASTORE'].data['watching'][uuid]

    # Should NOT raise / bail — must save as favicon.png
    watch.bump_favicon(url=data_uri, favicon_base_64=png_b64, mime_type='image/png')

    favicon_fname = watch.get_favicon_filename()
    assert favicon_fname is not None, "Favicon should have been saved"
    assert favicon_fname.endswith('.png'), f"Expected .png extension, got: {favicon_fname}"

    full_path = os.path.join(watch.data_dir, favicon_fname)
    assert os.path.getsize(full_path) == len(PNG_BYTES)

    # Also verify it's served correctly via the static route
    res = client.get(url_for('static_content', group='favicon', filename=uuid))
    assert res.status_code == 200
    assert res.data == PNG_BYTES


def test_favicon_mime_type_overrides_url_extension(client, live_server, measure_memory_usage, datastore_path):
    """
    mime_type parameter takes precedence over the URL path extension.
    A URL ending in .ico but with mime_type='image/png' should save as .png.
    """
    import base64
    import os

    PNG_BYTES = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
        b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    png_b64 = base64.b64encode(PNG_BYTES).decode()

    uuid = client.application.config.get('DATASTORE').add_watch(url='https://localhost')
    watch = live_server.app.config['DATASTORE'].data['watching'][uuid]

    watch.bump_favicon(url='https://example.com/favicon.ico', favicon_base_64=png_b64, mime_type='image/png')

    favicon_fname = watch.get_favicon_filename()
    assert favicon_fname is not None
    assert favicon_fname.endswith('.png'), f"mime_type should override URL extension, got: {favicon_fname}"


def test_favicon_oversized_rejected(client, live_server, measure_memory_usage, datastore_path):
    """Favicons larger than 1 MB must be silently dropped."""
    import base64
    import os

    oversized = b'\x00' * (1 * 1024 * 1024 + 1)
    oversized_b64 = base64.b64encode(oversized).decode()

    uuid = client.application.config.get('DATASTORE').add_watch(url='https://localhost')
    watch = live_server.app.config['DATASTORE'].data['watching'][uuid]

    result = watch.bump_favicon(url='https://example.com/big.png', favicon_base_64=oversized_b64, mime_type='image/png')

    assert result is None, "bump_favicon should return None for oversized favicon"
    assert watch.get_favicon_filename() is None, "No favicon file should have been written"


def test_bad_access(client, live_server, measure_memory_usage, datastore_path):

    res = client.post(
        url_for("imports.import_page"),
        data={"urls": 'https://localhost'},
        follow_redirects=True
    )

    assert b"1 Imported" in res.data
    wait_for_all_checks(client)

    # Attempt to add a body with a GET method
    res = client.post(
        url_for("ui.ui_edit.edit_page", uuid="first"),
        data={
              "url": 'javascript:alert(document.domain)',
              "tags": "",
              "method": "GET",
              "fetch_backend": "html_requests",
              "body": "",
              "time_between_check_use_default": "y"},
        follow_redirects=True
    )

    assert b'Watch protocol is not permitted or invalid URL format' in res.data

    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": '            javascript:alert(123)', "tags": ''},
        follow_redirects=True
    )

    assert b'Watch protocol is not permitted or invalid URL format' in res.data

    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": '%20%20%20javascript:alert(123)%20%20', "tags": ''},
        follow_redirects=True
    )

    assert b'Watch protocol is not permitted or invalid URL format' in res.data


    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": ' source:javascript:alert(document.domain)', "tags": ''},
        follow_redirects=True
    )

    assert b'Watch protocol is not permitted or invalid URL format' in res.data

    res = client.post(
        url_for("ui.ui_views.form_quick_watch_add"),
        data={"url": 'https://i-wanna-xss-you.com?hereis=<script>alert(1)</script>', "tags": ''},
        follow_redirects=True
    )

    assert b'Watch protocol is not permitted or invalid URL format' in res.data

def test_login_redirect_safe_urls(client, live_server, measure_memory_usage, datastore_path):
    """
    Test that safe redirect URLs work correctly in login flow.
    This verifies the fix for open redirect vulnerabilities while maintaining
    legitimate redirect functionality for both authenticated and unauthenticated users.
    """

    # Test 1: Accessing /login?redirect=/settings when not logged in
    # Should show the login form with redirect parameter preserved
    res = client.get(
        url_for("login", redirect="/settings"),
        follow_redirects=False
    )
    # Should show login form
    assert res.status_code == 200
    # Check that the redirect is preserved in the hidden form field
    assert b'name="redirect"' in res.data

    # Test 2: Valid internal redirect with query parameters
    res = client.get(
        url_for("login", redirect="/settings?tab=notifications"),
        follow_redirects=False
    )
    assert res.status_code == 200
    # Check that the redirect is preserved
    assert b'value="/settings?tab=notifications"' in res.data

    # Test 3: Malicious external URL should be blocked and default to watchlist
    res = client.get(
        url_for("login", redirect="https://evil.com/phishing"),
        follow_redirects=False
    )
    # Should show login form
    assert res.status_code == 200
    # The redirect parameter in the form should NOT contain the evil URL
    # Check the actual input value, not just anywhere in the page
    assert b'value="https://evil.com' not in res.data
    assert b'value="/evil.com' not in res.data
    assert b'name="redirect"' in res.data

    # Test 4: Double-slash attack should be blocked
    res = client.get(
        url_for("login", redirect="//evil.com"),
        follow_redirects=False
    )
    assert res.status_code == 200
    # Should not have the malicious URL in the redirect input value
    assert b'value="//evil.com"' not in res.data

    # Test 5: Protocol handler exploit should be blocked
    res = client.get(
        url_for("login", redirect="javascript:alert(document.domain)"),
        follow_redirects=False
    )
    assert res.status_code == 200
    # Should not have javascript: in the redirect input value
    assert b'value="javascript:' not in res.data

    # Test 6: At-symbol obfuscation attack should be blocked
    res = client.get(
        url_for("login", redirect="//@evil.com"),
        follow_redirects=False
    )
    assert res.status_code == 200
    # Should not have the malicious URL in the redirect input value
    assert b'value="//@evil.com"' not in res.data

    # Test 7: Multiple slashes attack should be blocked
    res = client.get(
        url_for("login", redirect="////evil.com"),
        follow_redirects=False
    )
    assert res.status_code == 200
    # Should not have the malicious URL in the redirect input value
    assert b'value="////evil.com"' not in res.data


