#!/usr/bin/env python3
# coding=utf-8

"""Unit tests for html_tools.html_to_text function."""

import hashlib
import threading
import unittest
from queue import Queue

from changedetectionio.html_tools import html_to_text


        # Extract text multiple times
        results = [html_to_text(html) for _ in range(10)]

        # All results should be identical
        assert len(set(results)) == 1, "html_to_text should be deterministic"

    def test_thread_safety_determinism(self):
        """
        Test that html_to_text produces deterministic output under high concurrency.

        This verifies that lxml's default parser (used by inscriptis.get_text)
        is thread-safe and produces consistent results when called from multiple
        threads simultaneously.
        """
        html = '''
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Main Heading</h1>
                <div class="content">
                    <p>First paragraph with <b>bold text</b>.</p>
                    <p>Second paragraph with <i>italic text</i>.</p>
                    <ul>
                        <li>Item 1</li>
                        <li>Item 2</li>
                        <li>Item 3</li>
                    </ul>
                </div>
            </body>
        </html>
        '''

        results_queue = Queue()

        def worker(worker_id, iterations=10):
            """Worker that converts HTML to text multiple times."""
            for i in range(iterations):
                text = html_to_text(html)
                md5 = hashlib.md5(text.encode('utf-8')).hexdigest()
                results_queue.put((worker_id, i, md5))

        # Launch many threads simultaneously
        num_threads = 50
        threads = []

        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Collect all MD5 results
        md5_values = []
        while not results_queue.empty():
            _, _, md5 = results_queue.get()
            md5_values.append(md5)

        # All MD5s should be identical
        unique_md5s = set(md5_values)

        assert len(unique_md5s) == 1, (
            f"Thread-safety issue detected! Found {len(unique_md5s)} different MD5 values: {unique_md5s}. "
            "The thread-local parser fix may not be working correctly."
        )

