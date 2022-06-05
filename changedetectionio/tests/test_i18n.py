#!/usr/bin/env python3

from flask import url_for
from .util import live_server_setup, wait_for_all_checks


def test_zh_TW(client, live_server, measure_memory_usage, datastore_path):
    import time
    test_url = url_for('test_endpoint', _external=True)

    # Be sure we got a session cookie
    res = client.get(url_for("watchlist.index"), follow_redirects=True)

    res = client.post(
        url_for("set_language", locale="zh_Hant_TW"), # Traditional
        follow_redirects=True
    )
    # HTML follows BCP 47 language tag rules, not underscore-based locale formats.
    assert b'<html lang="zh-Hant-TW"' in res.data
    assert b'Cannot set language without session cookie' not in res.data
    assert '選擇語言'.encode() in res.data

    # Check second set works
    res = client.post(
        url_for("set_language", locale="en_GB"),
        follow_redirects=True
    )
    assert b'Cannot set language without session cookie' not in res.data
    res = client.get(url_for("watchlist.index"), follow_redirects=True)
    assert b"Select Language" in res.data, "Second set of language worked"

    # Check arbitration between zh_Hant_TW<->zh
    res = client.post(
        url_for("set_language", locale="zh"), # Simplified chinese
        follow_redirects=True
    )
    res = client.get(url_for("watchlist.index"), follow_redirects=True)
    assert "选择语言".encode() in res.data, "Simplified chinese worked and it means the flask-babel cache worked"


def test_language_switching(client, live_server, measure_memory_usage, datastore_path, monkeypatch):
    """
    Test that the language switching functionality works correctly.

    1. Switch to Italian using the /set-language endpoint
    2. Verify that Italian text appears on the page
    3. Switch back to English and verify English text appears
    """

    # The Add-Watch page is only served when a browser that can render a live preview is
    # installed (it is the page this test reads translated processor labels off). A plain
    # test container has none - without PLAYWRIGHT_DRIVER_URL html_webdriver is Selenium,
    # which cannot - so pretend one exists rather than assert against a redirect.
    from changedetectionio.blueprint.add_watch_ui import browser_config
    monkeypatch.setattr(browser_config, 'list_visual_browser_choices',
                        lambda datastore: [('html_webdriver', 'WebDriver Chrome/Javascript')])

    # Establish session cookie
    client.get(url_for("add_watch_ui.add_watch_ui_index"), follow_redirects=True)

    # Step 1: Set the language to Italian using the /set-language endpoint
    res = client.post(
        url_for("set_language", locale="it"),
        follow_redirects=True
    )

    assert res.status_code == 200

    # Step 2: Request the index page - should be in Italian
    # The session cookie should be maintained by the test client
    res = client.get(
        url_for("add_watch_ui.add_watch_ui_index"),
        follow_redirects=True
    )

    assert res.status_code == 200

    # Check rendering switched to Italian. <html lang="..."> is set directly
    # from get_locale() so it can't be a translation accident — use it as the
    # canonical "what locale rendered?" signal instead of free-text sentinels
    # like 'Cancel', which can silently match a substring of a translated word
    # in another language (e.g. Italian 'Cancella' contains 'Cancel').
    assert b'<html lang="it"' in res.data, "Expected <html lang=\"it\"> after switching to Italian"
    # One strong content check too — confirms the catalogue was actually loaded
    # and the substitution happened, not just the lang attribute.
    assert b'Modifiche testo/HTML, JSON e PDF' in res.data, "Expected italian from processors.available_processors()"

    # Step 3: Switch back to English
    # NB: use 'en_GB' not 'en' — only the variants are in language_codes; the
    # plain 'en' code is silently rejected by set_language and the locale would
    # remain at 'it', defeating the round-trip assertion below.
    res = client.post(
        url_for("set_language", locale="en_GB"),
        follow_redirects=True
    )

    assert res.status_code == 200

    # Request the index page - should now be in English
    res = client.get(
        url_for("add_watch_ui.add_watch_ui_index"),
        follow_redirects=True
    )

    assert res.status_code == 200

    # Round-tripped back to English — assert via the lang attribute (the only
    # signal that can't be tricked by substring overlap from another locale).
    assert b'<html lang="en-GB"' in res.data, "Expected <html lang=\"en-GB\"> after switching back to English"


