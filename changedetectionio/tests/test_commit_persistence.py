#!/usr/bin/env python3
"""
Tests for immediate commit-based persistence system.

Tests cover:
- Watch.commit() persistence to disk
- Concurrent commit safety (race conditions)
- Processor config separation
- Data loss prevention (settings, tags, watch modifications)
"""

import json
import os
import threading
import time
from flask import url_for
from .util import wait_for_all_checks


# ==============================================================================
# 2. Commit() Persistence Tests
# ==============================================================================

def test_watch_commit_persists_to_disk(client, live_server):
    """Test that watch.commit() actually writes to watch.json immediately"""
    datastore = client.application.config.get('DATASTORE')

    # Create a watch
    uuid = datastore.add_watch(url='http://example.com', extras={'title': 'Original Title'})
    watch = datastore.data['watching'][uuid]

    # Modify and commit
    watch['title'] = 'Modified Title'
    watch['paused'] = True
    watch.commit()

    # Read directly from disk (bypass datastore cache)
    watch_json_path = os.path.join(watch.data_dir, 'watch.json')
    assert os.path.exists(watch_json_path), "watch.json should exist on disk"

    with open(watch_json_path, 'r') as f:
        disk_data = json.load(f)

    assert disk_data['title'] == 'Modified Title', "Title should be persisted to disk"
    assert disk_data['paused'] == True, "Paused state should be persisted to disk"
    assert disk_data['uuid'] == uuid, "UUID should match"


def test_concurrent_watch_commits_dont_corrupt(client, live_server):
    """Test that simultaneous commits to same watch don't corrupt JSON"""
    datastore = client.application.config.get('DATASTORE')

    uuid = datastore.add_watch(url='http://example.com', extras={'title': 'Test'})
    watch = datastore.data['watching'][uuid]

    errors = []

    def modify_and_commit(field, value):
        try:
            watch[field] = value
            watch.commit()
        except Exception as e:
            errors.append(e)

    # Run 10 concurrent commits
    threads = []
    for i in range(10):
        t = threading.Thread(target=modify_and_commit, args=('title', f'Title {i}'))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Should not have any errors
    assert len(errors) == 0, f"Expected no errors, got: {errors}"

    # JSON file should still be valid (not corrupted)
    watch_json_path = os.path.join(watch.data_dir, 'watch.json')
    with open(watch_json_path, 'r') as f:
        data = json.load(f)  # Should not raise JSONDecodeError
        assert data['uuid'] == uuid, "UUID should still be correct"
        assert 'Title' in data['title'], "Title should contain 'Title'"


def test_concurrent_modifications_during_commit(client, live_server):
    """Test that modifying watch during commit doesn't cause RuntimeError"""
    datastore = client.application.config.get('DATASTORE')

    uuid = datastore.add_watch(url='http://example.com', extras={'title': 'Test'})
    watch = datastore.data['watching'][uuid]

    errors = []
    stop_flag = threading.Event()

    def keep_modifying():
        """Continuously modify watch"""
        try:
            i = 0
            while not stop_flag.is_set():
                watch['title'] = f'Title {i}'
                watch['paused'] = i % 2 == 0
                i += 1
                time.sleep(0.001)
        except Exception as e:
            errors.append(('modifier', e))

    def keep_committing():
        """Continuously commit watch"""
        try:
            for _ in range(20):
                watch.commit()
                time.sleep(0.005)
        except Exception as e:
            errors.append(('committer', e))

    # Start concurrent modification and commits
    modifier = threading.Thread(target=keep_modifying)
    committer = threading.Thread(target=keep_committing)

    modifier.start()
    committer.start()

    committer.join()
    stop_flag.set()
    modifier.join()

    # Should not have RuntimeError from dict changing during iteration
    runtime_errors = [e for source, e in errors if isinstance(e, RuntimeError)]
    assert len(runtime_errors) == 0, f"Should not have RuntimeError, got: {runtime_errors}"


