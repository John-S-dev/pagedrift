from flask_socketio import SocketIO
from flask_babel import gettext

import time
import os
from loguru import logger
from blinker import signal

from changedetectionio import strtobool


class SignalHandler:
    """A standalone class to receive signals"""

    def __init__(self, socketio_instance, datastore):
        self.socketio_instance = socketio_instance
        self.datastore = datastore

        # Connect to the watch_check_update signal
        from changedetectionio.flask_app import watch_check_update as wcc
        wcc.connect(self.handle_signal, weak=False)
        #        logger.info("SignalHandler: Connected to signal from direct import")

        # Connect to the queue_length signal
        queue_length_signal = signal('queue_length')
        queue_length_signal.connect(self.handle_queue_length, weak=False)
        #       logger.info("SignalHandler: Connected to queue_length signal")

        watch_delete_signal = signal('watch_deleted')
        watch_delete_signal.connect(self.handle_deleted_signal, weak=False)

        watch_favicon_bumped_signal = signal('watch_favicon_bump')
        watch_favicon_bumped_signal.connect(self.handle_watch_bumped_favicon_signal, weak=False)

        watch_small_status_comment_signal = signal('watch_small_status_comment')
        watch_small_status_comment_signal.connect(self.handle_watch_small_status_update, weak=False)

        # Connect to the notification_event signal
        notification_event_signal = signal('notification_event')
        notification_event_signal.connect(self.handle_notification_event, weak=False)
        logger.info("SignalHandler: Connected to notification_event signal")

        # One-shot stats refresh for bulk operations that deliberately skip the per-watch
        # signal (see set_last_viewed(send_signal=False)) — n signals would mean n full
        # rescans of every watch plus 3n broadcasts.
        general_stats_signal = signal('general_stats_update')
        general_stats_signal.connect(self.handle_general_stats_update, weak=False)


    def handle_general_stats_update(self, *args, **kwargs):
        """Emit the global counters once, without touching any individual row.

        Sent after a bulk operation. The tab that triggered it is usually reloading anyway;
        this is for OTHER open tabs so their unread/error counters don't sit stale.
        Note their ROWS still keep a stale 'unviewed' class until the row resync lands —
        tracked separately, this only fixes the counters.
        """
        try:
            errored_count = sum(1 for w in self.datastore.data['watching'].values() if w.get('last_error'))
            self.socketio_instance.emit("general_stats_update", {
                'count_errors': errored_count,
                'unread_changes_count': self.datastore.unread_changes_count,
            })
            logger.trace("Socket.IO: Emitted one-shot general_stats_update")
        except Exception as e:
            logger.error(f"Socket.IO error in handle_general_stats_update: {str(e)}")

        general_stats = {
            'count_errors': errored_count,
            'unread_changes_count': datastore.unread_changes_count
        }

        # Debug what's being emitted
        # logger.debug(f"Emitting 'watch_update' event for {watch.get('uuid')}, data: {watch_data}")

        # Emit to all clients (no 'broadcast' parameter needed - it's the default behavior)
        socketio.emit("watch_update", {'watch': watch_data})
        socketio.emit("general_stats_update", general_stats)

        # The set of running UUIDs changes exactly when a worker claims/releases a watch,
        # and this signal fires at both of those moments - so emit the live "checking now" count here.
        socketio.emit("checking_now", {
            "count": len(running_uuids),
            "event_timestamp": time.time()
        })

        # Log after successful emit - use watch_data['uuid'] to avoid variable shadowing issues
        logger.trace(f"Socket.IO: Emitted update for watch {watch_data['uuid']}, Checking now: {watch_data['checking_now']}")

    except Exception as e:
        logger.error(f"Socket.IO error in handle_watch_update: {str(e)}")


