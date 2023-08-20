#!/usr/bin/env python3

import time
from copy import copy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import url_for
from .util import  live_server_setup, wait_for_all_checks, extract_UUID_from_client, delete_all_watches
from ..forms import REQUIRE_ATLEAST_ONE_TIME_PART_MESSAGE_DEFAULT, REQUIRE_ATLEAST_ONE_TIME_PART_WHEN_NOT_GLOBAL_DEFAULT


def test_check_basic_global_scheduler_functionality(client, live_server, measure_memory_usage, datastore_path):
    
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    test_url = url_for('test_random_content_endpoint', _external=True)

    uuid = client.application.config.get('DATASTORE').add_watch(url=test_url)
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    wait_for_all_checks(client)
    uuid = next(iter(live_server.app.config['DATASTORE'].data['watching']))

    # Setup all the days of the weeks using XXX as the placeholder for monday/tuesday/etc

    tpl = {
        "requests-time_schedule_limit-XXX-start_time": "00:00",
        "requests-time_schedule_limit-XXX-duration-hours": 24,
        "requests-time_schedule_limit-XXX-duration-minutes": 0,
        "requests-time_schedule_limit-XXX-enabled": '',  # All days are turned off
        "requests-time_schedule_limit-enabled": 'y',  # Scheduler is enabled, all days however are off.
    }

    scheduler_data = {}
    for day in days:
        for key, value in tpl.items():
            # Replace "XXX" with the current day in the key
            new_key = key.replace("XXX", day)
            scheduler_data[new_key] = value

    data = {
        "application-empty_pages_are_a_change": "",
        "application-scheduler_timezone_default": "Pacific/Kiritimati",  # Most Forward Time Zone (UTC+14:00)
        'application-fetch_backend': "html_requests",
        "requests-time_between_check-hours": 0,
        "requests-time_between_check-minutes": 0,
        "requests-time_between_check-seconds": 1,
    }
    data.update(scheduler_data)

    #####################
    res = client.post(
        url_for("settings.settings_page"),
        data=data,
        follow_redirects=True
    )

    assert b"Settings updated." in res.data

    res = client.get(url_for("settings.settings_page"))
    assert b'Pacific/Kiritimati' in res.data

    wait_for_all_checks(client)

    # UI Sanity check

    res = client.get(url_for("ui.ui_edit.edit_page", uuid="first"))
    assert b"Pacific/Kiritimati" in res.data, "Should be Pacific/Kiritimati in placeholder data"

    #### HITTING SAVE SHOULD NOT TRIGGER A CHECK
    last_check = live_server.app.config['DATASTORE'].data['watching'][uuid]['last_checked']
    res = client.post(
        url_for("ui.ui_edit.edit_page", uuid="first"),
        data={
            "url": test_url,
            "fetch_backend": "html_requests",
            "time_between_check_use_default": "y"},
        follow_redirects=True
    )
    assert b"Updated watch." in res.data
    time.sleep(2)
    assert live_server.app.config['DATASTORE'].data['watching'][uuid]['last_checked'] == last_check

    # Enabling "today" in Kiritimati time should make the system check that watch
    kiritimati_time = datetime.now(timezone.utc).astimezone(ZoneInfo("Pacific/Kiritimati"))
    kiritimati_time_day_of_week = kiritimati_time.strftime("%A").lower()
    live_server.app.config['DATASTORE'].data['settings']['requests']['time_schedule_limit'][kiritimati_time_day_of_week]["enabled"] = True

    time.sleep(3)
    assert live_server.app.config['DATASTORE'].data['watching'][uuid]['last_checked'] != last_check

    # Cleanup everything
    delete_all_watches(client)


