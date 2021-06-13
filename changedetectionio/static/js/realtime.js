// Socket.IO client-side integration for changedetection.io

$(document).ready(function () {

    function reapplyTableStripes() {
        $('.watch-table tbody tr').each(function(index) {
            $(this).removeClass('pure-table-odd pure-table-even');
            $(this).addClass(index % 2 === 0 ? 'pure-table-odd' : 'pure-table-even');
        });
    }

    function bindSocketHandlerButtonsEvents(socket) {
        $('.ajax-op').on('click.socketHandlerNamespace', function (e) {
            e.preventDefault();
            const op = $(this).data('op');
            const uuid = $(this).closest('tr').data('watch-uuid');
            
            console.log(`Socket.IO: Sending watch operation '${op}' for UUID ${uuid}`);
            
            // Emit the operation via Socket.IO
            socket.emit('watch_operation', {
                'op': op,
                'uuid': uuid
            });
            
            return false;
        });


        // Only the actual operation buttons carry name="op"; this excludes UI-only
        // buttons in the bar such as "Invert" (client-side selection toggle).
        $('#checkbox-operations button[name="op"]').on('click.socketHandlerNamespace', function (e) {
            e.preventDefault();
            const $button = $(this);
            const op = $button.val();
            // The cross-page selection store (watch-overview.js) is the source of
            // truth when present — it includes rows selected on other pages, not
            // just the visible checked boxes. Fall back to the DOM if absent.
            const watchSel = window.cdioWatchSelection;
            const checkedUuids = watchSel
                ? watchSel.all()
                : $('input[name="uuids"]:checked').map(function () {
                    return this.value.trim();
                }).get();

            // Check if this button requires confirmation
            console.log('Button clicked, op:', op, 'requires-confirm:', $button.is('[data-requires-confirm]'));
            if ($button.is('[data-requires-confirm]')) {
                console.log('Showing modal confirmation for operation:', op);
                const config = {
                    type: $button.data('confirm-type') || 'danger',
                    title: $button.data('confirm-title') || 'Confirm Action',
                    message: $button.data('confirm-message') || '<p>Are you sure you want to proceed?</p>',
                    confirmText: $button.data('confirm-button') || 'Confirm',
                    cancelText: $button.data('cancel-button') || 'Cancel',
                    onConfirm: function() {
                        console.log(`Socket.IO: Sending watch operation '${op}' for UUIDs:`, checkedUuids);
                        socket.emit('checkbox-operation', {
                            op: op,
                            uuids: checkedUuids,
                            extra_data: $('#op_extradata').val()
                        });
                        // Keep the rows selected after the operation so further
                        // actions can be applied to the same selection — except
                        // delete, where the rows (and their UUIDs) are now gone.
                        if (op === 'delete' && watchSel) {
                            watchSel.clear();
                            if (watchSel.refreshUI) watchSel.refreshUI();
                        }
                    }
                };
                ModalDialog.confirm(config);
            } else {
                console.log(`Socket.IO: Sending watch operation '${op}' for UUIDs:`, checkedUuids);
                socket.emit('checkbox-operation', {
                    op: op,
                    uuids: checkedUuids,
                    extra_data: $('#op_extradata').val()
                });
                // Keep the rows selected after the operation so further actions
                // can be applied to the same selection.
            }

            return false;
        });

    }


            socket.on('watch_small_status_comment', function (data) {
                console.log(`Socket.IO: Operation  watch_small_status_comment'${data.uuid}' status ${data.status}`);
                $('tr[data-watch-uuid="' + data.uuid + '"] td.last-checked .status-text').html("&nbsp;").text(data.status);
            });

            socket.on('notification_event', function (data) {
                console.log(`Stub handler for notification_event ${data.watch_uuid}`)
            });

            socket.on('watch_deleted', function (data) {
                $('tr[data-watch-uuid="' + data.uuid + '"] td').fadeOut(500, function () {
                    $(this).closest('tr').remove();
                    reapplyTableStripes();
                });
            });

            // So that the favicon is only updated when the server has written the scraped favicon to disk.
            socket.on('watch_bumped_favicon', function (watch) {
                const $watchRow = $(`tr[data-watch-uuid="${watch.uuid}"]`);
                if ($watchRow.length) {
                    $watchRow.addClass('has-favicon');
                    // Because the event could be emitted from a process that is outside the app context, url_for() might not work.
                    // Lets use url_for at template generation time to give us a PLACEHOLDER instead
                    let favicon_url = favicon_baseURL.replace('/PLACEHOLDER', `/${watch.uuid}?cache=${watch.event_timestamp}`);
                    console.log(`Setting favicon for UUID - ${watch.uuid} - ${favicon_url}`);
                    $('img.favicon', $watchRow).attr('src', favicon_url);
                }
            })

            socket.on('general_stats_update', function (general_stats) {
                // Drives the "Mark all viewed" button, which is always in the DOM and revealed by
                // this class (see body.has-any-unviewed in _watch_table.scss). Emitted whenever a
                // worker finishes a watch, and once after bulk ops like mark-all-viewed - so every
                // open tab shows/hides the button without needing a reload.
                document.body.classList.toggle('has-any-unviewed', general_stats.unread_changes_count !== 0);
                $('#watch-table-wrapper').toggleClass("has-unread-changes", general_stats.unread_changes_count !==0)
                $('#watch-table-wrapper').toggleClass("has-error", general_stats.count_errors !== 0)
                // NB: the watch-list status .seg counts (unread/errors/deals) are
                // server-rendered and SCOPED to the current tag/processor/search, so we
                // deliberately don't overwrite them here with these GLOBAL totals — doing
                // so would show e.g. the whole-list unread count on a filtered view.

                // The left-rail "Page Watches" unread badge IS global — keep it live.
                const unreadText = new Intl.NumberFormat(navigator.language).format(general_stats.unread_changes_count);
                $('.js-unread-count').text(unreadText).toggle(general_stats.unread_changes_count !== 0);
            });

            socket.on('watch_update', function (data) {
                const watch = data.watch;

                // Updating watch table rows
                const $watchRow = $('tr[data-watch-uuid="' + watch.uuid + '"]');
                console.log('Found watch row elements:', $watchRow.length);

