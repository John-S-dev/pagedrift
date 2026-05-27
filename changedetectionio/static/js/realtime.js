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


