"""Watch-list filtering — the single source of truth for "which watches match the
current view".

Shared by the watch list (the rendered table + the /uuids endpoint) and by the
bulk actions in the ui blueprint (mark-all-viewed, recheck-all) so a filtered view
and any action taken on it always operate on the SAME set. Keeping these as plain
functions (rather than duplicated per blueprint) is what stops the action buttons
from drifting away from the list's filter.
"""


def resolve_active_tag_uuid(datastore, active_tag_req):
    if not active_tag_req:
        return None
    for uuid, tag in datastore.data['settings']['application'].get('tags', {}).items():
        if active_tag_req == tag.get('title', '').lower().strip() or active_tag_req == uuid:
            return uuid
    return None


def list_filters_from_args(datastore, args):
    active_tag_req = (args.get('tag') or '').lower().strip()
    return {
        'with_errors': args.get('with_errors') == "1",
        'unread_only': args.get('unread') == "1",
        'deals': args.get('deals') == "1",
        'processor': (args.get('processor') or '').strip(),
        'tag_uuid': resolve_active_tag_uuid(datastore, active_tag_req),
        'search_q': args.get('q').strip().lower() if args.get('q') else False,
    }


