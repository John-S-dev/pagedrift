from .util import live_server_setup, wait_for_all_checks
from flask import url_for
from changedetectionio import __version__
import re
import time

        assert b"Password protection enabled." in res.data

        # Check we hit the login
        res = c.get(url_for("watchlist.index"), follow_redirects=True)
        # Should be logged out
        assert b"Login" in res.data
        # The login page must not leak the running version via the static asset cache-busters (#2190)
        assert not re.search(rb'\?v(?:er)?=' + re.escape(__version__.encode()), res.data)

        # The diff page should return something valid when logged out
        res = c.get(url_for("ui.ui_diff.diff_history_page", uuid="first"))
        assert b'Random content' in res.data

        # GHSA-vwgh-2hvh-4xm5: shared_diff_access only covers the read-only
        # diff page — the extract endpoints (which run an attacker-supplied
        # regex against history and write a CSV to disk) must still require
        # auth even when the share flag is enabled.
        res = c.get(url_for("ui.ui_diff.diff_history_page_extract_GET", uuid="first"))
        assert res.status_code == 302, "Extract form GET must redirect to login for anonymous users"
        assert b'/login' in res.data or b'login' in res.headers.get('Location', '').encode()

        res = c.post(
            url_for("ui.ui_diff.diff_history_page_extract_POST", uuid="first"),
            data={"extract_regex": ".*", "extract_submit_button": "Extract as CSV"},
        )
        assert res.status_code == 302, "Extract POST must redirect to login for anonymous users"
        assert b'login' in res.headers.get('Location', '').encode()

        # But sub-resources the diff page legitimately loads should still pass the gate.
        # download_patch is linked from diff.html — anonymous viewers must be able to fetch it.
        # (We don't care about the body here, just that auth doesn't block it.)
        res = c.get(url_for("ui.ui_diff.download_patch", uuid="first"))
        assert res.status_code != 302, "download_patch must be reachable for shared diff viewers"

        # processor_asset (used for screenshots embedded in image_ssim_diff watches) must also be reachable.
        # For a text watch the processor has no such asset so 404 is fine — what matters is no auth redirect.
        res = c.get(url_for("ui.ui_diff.processor_asset", uuid="first", asset_name="before"))
        assert res.status_code != 302, "processor_asset must be reachable for shared diff viewers"

        # access to assets should work (check_authentication)
        res = c.get(url_for('static_content', group='js', filename='jquery-3.6.0.min.js'))
        assert res.status_code == 200
        res = c.get(url_for('static_content', group='styles', filename='styles.css'))
        assert res.status_code == 200
        res = c.get(url_for('static_content', group='styles', filename='404-testetest.css'))
        assert res.status_code == 404

        # Access to screenshots should be limited by 'shared_diff_access'
        path = url_for('static_content', group='screenshot', filename='random-uuid-that-will-404.png', _external=True)
        res = c.get(path)
        assert res.status_code == 404

        # Check wrong password does not let us in
        res = c.post(
            url_for("login"),
            data={"password": "WRONG PASSWORD"},
            follow_redirects=True
        )

        assert b"/logout" not in res.data
        assert b"Incorrect password" in res.data


        # Menu should not be available yet
        #        assert b"SETTINGS" not in res.data
        #        assert b"BACKUP" not in res.data
        #        assert b"IMPORT" not in res.data

        # defaultuser@changedetection.io is actually hardcoded for now, we only use a single password
        res = c.post(
            url_for("login"),
            data={"password": "foobar"},
            follow_redirects=True
        )

