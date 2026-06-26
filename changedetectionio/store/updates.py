"""
Schema update migrations for the datastore.

This module contains all schema version upgrade methods (update_1 through update_N).
These are mixed into ChangeDetectionStore to keep the main store file focused.

IMPORTANT: Each update could be run even when they have a new install and the schema is correct.
Therefore - each `update_n` should be very careful about checking if it needs to actually run.
"""

def create_backup_tarball(datastore_path, update_number):
    """
    Create a tarball backup of the entire datastore structure before running an update.

    Includes:
    - All {uuid}/watch.json files
    - All {uuid}/tag.json files
    - changedetection.json (settings, if it exists)
    - url-watches.json (legacy format, if it exists)
    - Directory structure preserved

    Args:
        datastore_path: Path to datastore directory
        update_number: Update number being applied

    Returns:
        str: Path to created tarball, or None if backup failed

    Restoration:
    To restore from a backup:
        cd /path/to/datastore
        tar -xzf before-update-N-timestamp.tar.gz
    This will restore all watch.json and tag.json files and settings to their pre-update state.
    """
    timestamp = int(time.time())
    backup_filename = f"before-update-{update_number}-{timestamp}.tar.gz"
    backup_path = os.path.join(datastore_path, backup_filename)

