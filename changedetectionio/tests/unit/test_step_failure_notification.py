"""
Unit test for send_step_failure_notification regression.

Before the fix, line 499 called self._check_cascading_vars('notification_format', watch)
which raises AttributeError because _check_cascading_vars is a module-level function,
not a method of NotificationService.
"""

