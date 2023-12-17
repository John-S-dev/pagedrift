#!/usr/bin/env python3

# run from dir above changedetectionio/ dir
# python3 -m unittest changedetectionio.tests.unit.test_notification_diff

import unittest
import os

from changedetectionio import diff
from changedetectionio.diff import (
    REMOVED_PLACEMARKER_OPEN,
    REMOVED_PLACEMARKER_CLOSED,
    ADDED_PLACEMARKER_OPEN,
    ADDED_PLACEMARKER_CLOSED,
    CHANGED_PLACEMARKER_OPEN,
    CHANGED_PLACEMARKER_CLOSED,
    CHANGED_INTO_PLACEMARKER_OPEN,
    CHANGED_INTO_PLACEMARKER_CLOSED,
    extract_changed_from,
    extract_changed_to,
)


    def test_expected_diff_patch_output(self):
        base_dir = os.path.dirname(__file__)
        with open(base_dir + "/test-content/before.txt", 'r') as f:
            before = f.read()
        with open(base_dir + "/test-content/after.txt", 'r') as f:
            after = f.read()

        output = diff.render_diff(previous_version_file_contents=before,
                                  newest_version_file_contents=after,
                                  patch_format=True)

        

        output = output.split("\n")

        self.assertIn('-ok', output)
        self.assertIn('+xok', output)
        self.assertIn('+next-x-ok', output)
        self.assertIn('+and something new', output)

        # @todo test blocks of changed, blocks of added, blocks of removed

    def test_word_level_diff(self):
        """Test word-level diff functionality"""
        before = "The quick brown fox jumps over the lazy dog"
        after = "The fast brown cat jumps over the lazy dog"

        # Test with word_diff enabled
        output = diff.render_diff(before, after, include_equal=False, word_diff=True)
        # Should highlight only changed words, not entire line
        self.assertIn(f'{REMOVED_PLACEMARKER_OPEN}quick{REMOVED_PLACEMARKER_CLOSED}', output)
        self.assertIn(f'{ADDED_PLACEMARKER_OPEN}fast{ADDED_PLACEMARKER_CLOSED}', output)
        self.assertIn(f'{REMOVED_PLACEMARKER_OPEN}fox{REMOVED_PLACEMARKER_CLOSED}', output)
        self.assertIn(f'{ADDED_PLACEMARKER_OPEN}cat{ADDED_PLACEMARKER_CLOSED}', output)
        # Unchanged words should appear without markers
        self.assertIn('brown', output)
        self.assertIn('jumps', output)

        # Test with word_diff disabled (line-level)
        output = diff.render_diff(before, after, include_equal=False, word_diff=False)
        # Should show full line changes
        self.assertIn(f'{CHANGED_PLACEMARKER_OPEN}The quick brown fox jumps over the lazy dog{CHANGED_PLACEMARKER_CLOSED}', output)
        self.assertIn(f'{CHANGED_INTO_PLACEMARKER_OPEN}The fast brown cat jumps over the lazy dog{CHANGED_INTO_PLACEMARKER_CLOSED}', output)

    def test_word_level_diff_html(self):
        """Test word-level diff with HTML coloring"""
        before = "110 points by user"
        after = "111 points by user"

        output = diff.render_diff(before, after, include_equal=False, word_diff=True)
        # Unchanged text should not be wrapped in spans
        self.assertIn('points by user', output)
        self.assertIn('11', output)  # Common prefix is unchanged

        # The inner HTML uses REMOVED_INNER_STYLE and ADDED_INNER_STYLE for character-level highlighting
        expected = f'{REMOVED_PLACEMARKER_OPEN}110{REMOVED_PLACEMARKER_CLOSED}{ADDED_PLACEMARKER_OPEN}111{ADDED_PLACEMARKER_CLOSED} points by user'
        self.assertEqual(output, expected)



    def test_context_lines(self):
        """Test context_lines parameter"""
        before = """Line 1
Line 2
Line 3
Old line
Line 5
Line 6
Line 7
Another old
Line 9
Line 10"""

        after = """Line 1
Line 2
Line 3
New line
Line 5
Line 6
Line 7
Another new
Line 9
Line 10"""

        # Test with no context
        output = diff.render_diff(before, after, include_equal=False, context_lines=0, word_diff=True)
        
        lines = output.split("\n")
        # Should only show changed lines
        self.assertEqual(len([l for l in lines if l.strip()]), 2)  # Two changed lines
        self.assertIn(f'{REMOVED_PLACEMARKER_OPEN}Old{REMOVED_PLACEMARKER_CLOSED}', output)
        self.assertIn(f'{ADDED_PLACEMARKER_OPEN}New{ADDED_PLACEMARKER_CLOSED}', output)

        # Test with 1 line of context
        output = diff.render_diff(before, after, include_equal=False, context_lines=1, word_diff=True)
        
