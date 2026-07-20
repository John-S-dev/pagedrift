$(function () {
    function normalizeUrl(el) {
        const val = el.value.trim();
        if (val && !/^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(val)) {
            el.value = 'https://' + val;
        }
    }

    $('#url').on('blur keydown', function (e) {
        if (e.type === 'blur' || e.key === 'Enter') {
            normalizeUrl(this);
        }
    });

    $('form').on('submit', function () {
        normalizeUrl($('#url')[0]);
    });

    // Remove unviewed status when normally clicked
    $('.diff-link').click(function () {
        $(this).closest('.unviewed').removeClass('unviewed');
    });

    $('td[data-timestamp]').each(function () {
        $(this).prop('title', new Intl.DateTimeFormat(undefined,
            {
                dateStyle: 'full',
                timeStyle: 'long'
            }).format($(this).data('timestamp') * 1000));
    })

    $("#checkbox-assign-tag").click(function (e) {
        $('#op_extradata').val(prompt("Enter a tag name"));
    });

    // Bulk "Browser" / "Proxy" actions: open a modal with the same radio choices as the
    // edit page, then set #op_extradata and fire the (hidden) real operation button so the
    // existing socket.io / form submit path applies the choice to the selected watches.
    // Title / button text come from the button's data-* attributes so they pass through
    // server-side i18n (the static JS can't call gettext itself).
    function showBulkChoiceModal($btn, templateId, radioName, hiddenBtnId) {
        const tmpl = document.getElementById(templateId);
        if (!tmpl || typeof ModalDialog === 'undefined') {
            return;
        }
        ModalDialog.confirm({
            type: 'info',
            title: $btn.data('modal-title'),
            message: '<div class="bulk-choice-list">' + tmpl.innerHTML + '</div>',
            confirmText: $btn.data('modal-apply'),
            onConfirm: function () {
                const checked = document.querySelector('.modal-dialog input[name="' + radioName + '"]:checked');
                $('#op_extradata').val(checked ? checked.value : '');
                $('#' + hiddenBtnId).trigger('click');
                // Feedback is server-driven: the backend emits a 'toast' event with the real
                // count/result, handled in realtime.js (and the form fallback flashes on redirect).
            }
        });
    }

    $("#checkbox-set-browser").click(function (e) {
        showBulkChoiceModal($(this), 'bulk-browser-options', 'bulk-fetch-backend', 'op-set-fetch-backend');
    });

    $("#checkbox-set-proxy").click(function (e) {
        showBulkChoiceModal($(this), 'bulk-proxy-options', 'bulk-proxy', 'op-set-proxy');
    });


    $('.history-link').click(function (e) {
        // Incase they click 'back' in the browser, it should be removed.
        $(this).closest('tr').removeClass('unviewed');
    });

    // Inline restock price/stock graph: for restock_diff rows the History button rolls down a
    // price/stock graph (no LLM needed), styled like the AI summary roll-down. Registered before
    // the LLM handler and stops propagation so AI mode never turns these into LLM summaries.
    $(document).on('click', 'tr.processor-restock_diff .ai-history-btn', function (e) {
        e.preventDefault();
        e.stopImmediatePropagation();

        var i18n       = window.watchOverviewI18n || {};
        var $btn       = $(this);
        var uuid       = $btn.data('uuid');
        var dataUrl    = $btn.data('processor-data-url');
        var historyUrl = $btn.attr('href');
        var $row       = $btn.closest('tr');
        var rowId      = 'restock-graph-row-' + uuid;
        var cols       = $row.find('td').length;
        var $tbody     = $row.closest('tbody');

        $row.removeClass('unviewed');

        // Toggle off if already open
        if ($('#' + rowId).length) {
            $('#' + rowId).remove();
            $tbody.find('tr:not(.restock-inline-row) td').css('background-color', '');
            return;
        }

        // Freeze row backgrounds so inserting a <tr> doesn't shift nth-child striping
        var $dataRows = $tbody.find('tr:not(.restock-inline-row)');
        var bgMap = [];
        $dataRows.each(function () { bgMap.push($(this).find('td:first').css('background-color')); });

        var $r = $(
            '<tr class="restock-inline-row" id="' + rowId + '">' +
            '<td colspan="' + cols + '">' +
            '<div class="restock-inline-graph"></div>' +
            '<a class="restock-inline-history-link"></a>' +
            '</td></tr>'
        );
        $r.find('.restock-inline-graph').text(i18n.loadingPriceHistory || 'Loading price history…');
        $r.find('.restock-inline-history-link').attr('href', historyUrl).text(i18n.gotoHistory || 'Goto full history');
        $row.after($r);

        // Re-apply frozen backgrounds so the nth-child parity shift is invisible
        $dataRows.each(function (i) { $(this).find('td').css('background-color', bgMap[i]); });

        function showError() {
            $r.find('.restock-inline-graph').html(
                '<span class="restock-inline-error">' +
                $('<span>').text(i18n.priceHistoryError || 'Could not load price history.').html() +
                '</span>'
            );
        }

    // ---- Cross-page selection store -------------------------------------------
    // Selection is a Set of watch UUIDs (the source of truth) rather than the DOM,
    // so it spans paginated pages. Persisted in sessionStorage scoped to the
    // watch-list page + the active tag (only): a selection survives switching the
    // status/processor/search/pagination views, but each tag group (and the
    // untagged "all" view) gets its own selection bucket. The "/uuids" endpoint
    // supplies the full matching id list for "select all matching".
    const sel = window.cdioWatchSelection = (function () {
        const KEY = 'cdio-watch-selection';
        function scopeKey() {
            const tag = new URLSearchParams(location.search).get('tag') || '';
            return location.pathname + (tag ? '?tag=' + tag : '');
        }
        let uuids = new Set();
        try {
            const obj = JSON.parse(sessionStorage.getItem(KEY) || 'null');
            if (obj && obj.scope === scopeKey() && Array.isArray(obj.uuids)) {
                uuids = new Set(obj.uuids);
            }
        } catch (e) { /* private mode / corrupt — best effort */ }
        function persist() {
            try {
                sessionStorage.setItem(KEY, JSON.stringify({ scope: scopeKey(), uuids: Array.from(uuids) }));
            } catch (e) { /* quota / private mode */ }
        }
        return {
            has: (u) => uuids.has(u),
            add: (u) => { uuids.add(u); persist(); },
            remove: (u) => { uuids.delete(u); persist(); },
            toggle: (u) => { if (uuids.has(u)) { uuids.delete(u); } else { uuids.add(u); } persist(); },
            addMany: (arr) => { arr.forEach((u) => uuids.add(u)); persist(); },
            clear: () => { uuids.clear(); persist(); },
            all: () => Array.from(uuids),
            size: () => uuids.size
        };
    })();

    const selCfg = window.watchListSelection || {};
    const totalMatching = parseInt(selCfg.total, 10) || 0;

    // Row checkbox values carry a trailing space in the template — always trim.
    const cbUuid = (el) => (el.value || '').trim();
    const $rowCbs = () => $('input[name="uuids"][type=checkbox]');
    const fmtNum = (n) => new Intl.NumberFormat(navigator.language).format(n);

    // Reflect the store onto this page's checkboxes (load + after bulk changes).
    function applySelectionToDom() {
        $rowCbs().each(function () { this.checked = sel.has(cbUuid(this)); });
        const visible = $rowCbs().get();
        $('#check-all').prop('checked', visible.length > 0 && visible.every((el) => el.checked));
    }

    function updateRecordsSelected() {
        const $el = $('#records-selected');
        if (!$el.length) return;
        const n = sel.size();
        if (n > 0) {
            const tpl = $el.attr('data-template') || '%(count)s records selected';
            // Only the count is emphasised; the number is locale-formatted digits.
            $el.html(tpl.replace('%(count)s', '<strong>' + fmtNum(n) + '</strong>')).show();
        } else {
            $el.hide();
        }
    }

    // Check-all (this page only).
    $("#check-all").click(function () {
        const on = this.checked;
        $rowCbs().each(function () {
            this.checked = on;
            if (on) { sel.add(cbUuid(this)); } else { sel.remove(cbUuid(this)); }
        });
        refreshSelectionUI();
    });

    // Invert this page's selection.
    $("#check-invert").click(function () {
        $rowCbs().each(function () { sel.toggle(cbUuid(this)); });
        applySelectionToDom();
        refreshSelectionUI();
    });

    // Cancel: clear the whole cross-page selection (incl. the stored browser data)
    // and dismiss the operations bar.
    $("#check-cancel").click(function () {
        sel.clear();
        applySelectionToDom();
        refreshSelectionUI();
    });

    // "Select all N matching" — pull the full matching id list from the server.
    $(document).on('click', '#select-all-matching', function () {
        if (!selCfg.uuidsUrl) return;
        const $btn = $(this).prop('disabled', true);
        $.getJSON(selCfg.uuidsUrl + location.search)
            .done(function (data) {
                if (data && Array.isArray(data.uuids)) {
                    sel.addMany(data.uuids.map((u) => ('' + u).trim()));
                    applySelectionToDom();
                    refreshSelectionUI();
                }
            })
            .always(function () { $btn.prop('disabled', false); });
    });

    // "Clear selection" link inside the banner.
    $(document).on('click', '#select-all-clear', function () {
        sel.clear();
        applySelectionToDom();
        refreshSelectionUI();
    });

    const time_check_step_size_seconds=1;

    // On load: reflect any persisted selection onto this page, then refresh the UI.
    applySelectionToDom();
    refreshSelectionUI();

    setInterval(function () {
        // Background ETA completion for 'checking now'
        $(".watch-table .checking-now .last-checked").each(function () {
            const eta_complete = parseFloat($(this).data('eta_complete'));
            const fetch_duration = parseInt($(this).data('fetchduration'));

            if (eta_complete + 2 > nowtimeserver && fetch_duration > 3) {
                const remaining_seconds = Math.abs(eta_complete) - nowtimeserver - 1;

                let r = Math.round((1.0 - (remaining_seconds / fetch_duration)) * 100);
                if (r < 10) {
                    r = 10;
                }
                if (r >= 90) {
                    r = 100;
                }
                $(this).css('background-size', `${r}% 100%`);
            } else {
                // Snap to full complete
                $(this).css('background-size', `100% 100%`);
            }
        });

        nowtimeserver = nowtimeserver + time_check_step_size_seconds;
    }, time_check_step_size_seconds * 1000);

