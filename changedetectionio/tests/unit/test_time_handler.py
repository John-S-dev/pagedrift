#!/usr/bin/env python3

"""
Comprehensive tests for time_handler module refactored to use arrow.

import unittest
import unittest.mock
import arrow
from changedetectionio import time_handler


class TestAmIInsideTime(unittest.TestCase):
    """Tests for the am_i_inside_time function."""

    def test_current_time_within_schedule(self):
        """Test that current time is detected as within schedule."""
        # Get current time in a specific timezone
        timezone_str = 'Europe/Berlin'
        now = arrow.now(timezone_str)
        day_of_week = now.format('dddd')
        time_str = now.format('HH:00')  # Current hour, 0 minutes
        duration = 60  # 60 minutes

        result = time_handler.am_i_inside_time(
            day_of_week=day_of_week,
            time_str=time_str,
            timezone_str=timezone_str,
            duration=duration
        )

        self.assertTrue(result, f"Current time should be within {duration} minute window starting at {time_str}")

    def test_current_time_outside_schedule(self):
        """Test that time in the past is not within current schedule."""
        timezone_str = 'Europe/Berlin'
        # Get yesterday's date
        yesterday = arrow.now(timezone_str).shift(days=-1)
        day_of_week = yesterday.format('dddd')
        time_str = yesterday.format('HH:mm')
        duration = 30  # Only 30 minutes

        # Mock current time for testing
        with unittest.mock.patch('arrow.now', return_value=test_time):
            result = time_handler.am_i_inside_time(
                day_of_week=day_of_week,
                time_str="00:00",
                timezone_str=timezone_str,
                duration=1440  # 24 hours
            )
            self.assertTrue(result, "Should be active at start of 24-hour schedule")

    def test_24_hour_schedule_at_end_of_day(self):
        """Test 24-hour schedule is active at 23:59:59."""
        timezone_str = 'UTC'
        # Test at Monday 23:59:59
        test_time = arrow.get('2024-01-01 23:59:59', 'YYYY-MM-DD HH:mm:ss').replace(tzinfo=timezone_str)
        day_of_week = test_time.format('dddd')  # Monday

        with unittest.mock.patch('arrow.now', return_value=test_time):
            result = time_handler.am_i_inside_time(
                day_of_week=day_of_week,
                time_str="00:00",
                timezone_str=timezone_str,
                duration=1440  # 24 hours
            )
            self.assertTrue(result, "Should be active at end of 24-hour schedule")

    def test_24_hour_schedule_at_midnight_transition(self):
        """Test 24-hour schedule at exactly midnight transition."""
        timezone_str = 'UTC'
        # Test at Tuesday 00:00:00 (end of Monday's 24-hour schedule)
        test_time = arrow.get('2024-01-02 00:00:00', 'YYYY-MM-DD HH:mm:ss').replace(tzinfo=timezone_str)
        monday = test_time.shift(days=-1).format('dddd')  # Monday

        with unittest.mock.patch('arrow.now', return_value=test_time):
            result = time_handler.am_i_inside_time(
                day_of_week=monday,
                time_str="00:00",
                timezone_str=timezone_str,
                duration=1440  # 24 hours
            )
            self.assertTrue(result, "Should include exactly midnight at end of 24-hour schedule")

    def test_schedule_crosses_midnight_before_midnight(self):
        """Test schedule crossing midnight - before midnight."""
        timezone_str = 'UTC'
        # Monday 23:30
        test_time = arrow.get('2024-01-01 23:30:00', 'YYYY-MM-DD HH:mm:ss').replace(tzinfo=timezone_str)
        day_of_week = test_time.format('dddd')  # Monday

        with unittest.mock.patch('arrow.now', return_value=test_time):
            result = time_handler.am_i_inside_time(
                day_of_week=day_of_week,
                time_str="23:00",
                timezone_str=timezone_str,
                duration=120  # 2 hours (until 01:00 next day)
            )
            self.assertTrue(result, "Should be active before midnight in cross-midnight schedule")

    def test_schedule_crosses_midnight_after_midnight(self):
        """Test schedule crossing midnight - after midnight."""
        timezone_str = 'UTC'
        # Tuesday 00:30
        test_time = arrow.get('2024-01-02 00:30:00', 'YYYY-MM-DD HH:mm:ss').replace(tzinfo=timezone_str)
        monday = test_time.shift(days=-1).format('dddd')  # Monday

        with unittest.mock.patch('arrow.now', return_value=test_time):
            result = time_handler.am_i_inside_time(
                day_of_week=monday,
                time_str="23:00",
                timezone_str=timezone_str,
                duration=120  # 2 hours (until 01:00 Tuesday)
            )
            self.assertTrue(result, "Should be active after midnight in cross-midnight schedule")

    def test_schedule_crosses_midnight_at_exact_end(self):
        """Test schedule crossing midnight at exact end time."""
        timezone_str = 'UTC'
        # Tuesday 01:00 (exact end of Monday 23:00 + 120 minutes)
        test_time = arrow.get('2024-01-02 01:00:00', 'YYYY-MM-DD HH:mm:ss').replace(tzinfo=timezone_str)
        monday = test_time.shift(days=-1).format('dddd')  # Monday

