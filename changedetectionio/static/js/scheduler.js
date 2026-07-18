function getTimeInTimezone(timezone) {
    const now = new Date();
    const options = {
        timeZone: timezone,
        weekday: 'long',
        year: 'numeric',
        hour12: false,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
    };

    const formatter = new Intl.DateTimeFormat('en-US', options);
    return formatter.format(now);
}

$(document).ready(function () {

    let exceedsLimit = false;
    const warning_text = $("#timespan-warning")
    const timezone_text_widget = $("input[id*='time_schedule_limit-timezone']")

    toggleVisibility('#time_schedule_limit-enabled, #requests-time_schedule_limit-enabled', '#schedule-day-limits-wrapper', true)

    setInterval(() => {
        let success = true;
        try {
            // Show the current local time according to either placeholder or entered TZ name
            if (timezone_text_widget.val().length) {
                $('#local-time-in-tz').text(getTimeInTimezone(timezone_text_widget.val()));
            } else {
                // So maybe use what is in the placeholder (which will be the default settings)
                $('#local-time-in-tz').text(getTimeInTimezone(timezone_text_widget.attr('placeholder')));
            }
        } catch (error) {
            success = false;
            $('#local-time-in-tz').text("");
            console.error(timezone_text_widget.val())
        }

        $(timezone_text_widget).toggleClass('error', !success);

    }, 500);

    $('#schedule-day-limits-wrapper').on('change click blur', 'input, checkbox, select', function() {

        let allOk = true;

