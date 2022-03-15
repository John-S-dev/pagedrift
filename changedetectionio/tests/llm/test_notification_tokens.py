"""
Tests that {{ llm_summary }} and {{ llm_intent }} notification tokens
are correctly populated in the notification pipeline.

def _make_n_object(**extra):
    n = NotificationContextData()
    n.update({
        'notification_body': '',
        'notification_title': '',
        'notification_format': 'text',
        'notification_urls': ['json://localhost/'],
        'uuid': 'test-uuid',
        'watch_uuid': 'test-uuid',
        'watch_url': 'https://example.com',
        'current_snapshot': 'current text',
        'prev_snapshot': 'previous text',
    })
    n.update(extra)
    return n


