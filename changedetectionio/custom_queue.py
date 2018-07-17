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

class SignalPriorityQueue(queue.PriorityQueue):
    """
    Extended PriorityQueue that sends a signal when items with a UUID are added.
    
    This class extends the standard PriorityQueue and adds a signal emission
    after an item is put into the queue. If the item contains a UUID, the signal
    is sent with that UUID as a parameter.
    """
    
    def __init__(self, maxsize=0):
        super().__init__(maxsize)
        try:
            self.queue_length_signal = signal('queue_length')
        except Exception as e:
            logger.critical(f"Exception: {e}")

    def put(self, item, block=True, timeout=None):
        # Call the parent's put method first
        super().put(item, block, timeout)

        # After putting the item in the queue, check if it has a UUID and emit signal
        if hasattr(item, 'item') and isinstance(item.item, dict) and 'uuid' in item.item:
            uuid = item.item['uuid']
            # Get the signal and send it if it exists
            watch_check_update = signal('watch_check_update')
            if watch_check_update:
                # NOTE: This would block other workers from .put/.get while this signal sends
                # Signal handlers may iterate the queue/datastore while holding locks
                watch_check_update.send(watch_uuid=uuid)
        
        # Send queue_length signal with current queue size
        try:

            if self.queue_length_signal:
                self.queue_length_signal.send(length=self.qsize())
        except Exception as e:
            logger.critical(f"Exception: {e}")

    def get(self, block=True, timeout=None):
        # Call the parent's get method first
        item = super().get(block, timeout)
        
        # Send queue_length signal with current queue size
        try:
            if self.queue_length_signal:
                self.queue_length_signal.send(length=self.qsize())
        except Exception as e:
            logger.critical(f"Exception: {e}")
        return item
    
