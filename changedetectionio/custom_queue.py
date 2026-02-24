import queue
import asyncio
from blinker import signal
from loguru import logger


        # After putting the notification in the queue, emit signal with watch UUID
        try:
            if self.notification_event_signal and isinstance(item, dict):
                watch_uuid = item.get('uuid')
                if watch_uuid:
                    # Send the notification_event signal with the watch UUID
                    self.notification_event_signal.send(watch_uuid=watch_uuid)
                    logger.trace(f"NotificationQueue: Emitted notification_event signal for watch UUID {watch_uuid}")
                else:
                    # Send signal without UUID for system notifications
                    self.notification_event_signal.send()
                    logger.trace("NotificationQueue: Emitted notification_event signal for system notification")
        except Exception as e:
            logger.error(f"Exception emitting notification_event signal: {e}")

