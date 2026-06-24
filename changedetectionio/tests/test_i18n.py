#!/usr/bin/env python3

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


