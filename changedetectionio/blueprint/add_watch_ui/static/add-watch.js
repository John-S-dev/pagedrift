// Add Watch UI glue: fetch a live snapshot for the entered URL and drive the
// shared visual selector (window.initVisualSelector from visual-selector.js).

        $.ajax({
            url: add_watch_snapshot_url,
            // POST, never GET - this makes the server-side browser fetch a URL of our
            // choosing, so it must not be triggerable cross-origin. csrf.js adds the
            // X-CSRFToken header to every non-GET ajax call; the CSRF field on the form
            // is sent too so it works even if that handler hasn't run yet.
            method: 'POST',
            // Preview with the browser picked in the list - that same browser is what
            // gets saved on the watch, so what you see here is what it will check with.
            data: {
                url: url,
                fetch_backend: $('input[name="fetch_backend"]:checked').val() || '',
                csrf_token: $('#new-watch-form input[name="csrf_token"]').val() || '',
            },
            dataType: 'json',
        }).done((data) => {
            showState('ready');
            $temporaryUuid.val(data.temporary_uuid || '');
            vs.load({screenshotSrc: data.screenshot, xpathData: data.xpath_data});
        }).fail((xhr) => {
            const msg = (xhr && xhr.responseText) ? xhr.responseText : 'Could not fetch a preview for that URL.';
            $error.text(msg);
            showState('error');
        });
    }

    $go.on('click', fetchSnapshot);

    // Enter in the URL box should fetch a preview, not submit the whole form
    $url.on('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            fetchSnapshot();
        }
    });

    // "Select by element" toggles live hover/click element selection
    $byElement.on('change', function () {
        const on = $(this).is(':checked');
        vs.setSelectionEnabled(on);
        $xpathRow.toggle(on && $wrapper.is(':visible'));
        $clear.toggle(on && $wrapper.is(':visible'));
        if (!on) {
            $includeFilters.val('');
        }
    });

    showState('empty');
});
