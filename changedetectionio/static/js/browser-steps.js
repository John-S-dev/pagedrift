$(document).ready(function () {

    var browsersteps_session_id;
    var browser_interface_seconds_remaining = 0;
    var apply_buttons_disabled = false;
    var include_text_elements = $("#include_text_elements");
    var xpath_data = false;
    var current_selected_i;
    var state_clicked = false;
    var c;

    // redline highlight context
    var ctx;
    var last_click_xy = {'x': -1, 'y': -1}

    $(window).resize(function () {
        set_scale();
    });
    // Should always be disabled

    $('#browsersteps-click-start').click(function () {
        $("#browsersteps-click-start").fadeOut();
        $("#browsersteps-selector-wrapper .spinner").fadeIn();
        start();
    });

    $('a#browsersteps-tab').click(function () {
        reset();
    });

    window.addEventListener('hashchange', function () {
        if (window.location.hash == '#browser-steps') {
            reset();
        }
    });

    function reset() {
        xpath_data = false;
        $('#browsersteps-img').removeAttr('src');
        $("#browsersteps-click-start").show();
        $("#browsersteps-selector-wrapper .spinner").hide();
        browser_interface_seconds_remaining = 0;
        browsersteps_session_id = false;
        apply_buttons_disabled = false;
        ctx.clearRect(0, 0, c.width, c.height);
    }

    // Show seconds remaining until the browser interface needs to restart the session
    // (See comment at the top of changedetectionio/blueprint/browser_steps/__init__.py )
    setInterval(() => {
        if (browser_interface_seconds_remaining >= 1) {
            document.getElementById('browser-seconds-remaining').innerText = browser_interface_seconds_remaining + " seconds remaining in session";
            browser_interface_seconds_remaining -= 1;
        }
    }, "1000")


    function set_scale() {

        // some things to check if the scaling doesnt work
        // - that the widths/sizes really are about the actual screen size cat elements.json |grep -o width......|sort|uniq
        selector_image = $("img#browsersteps-img")[0];
        selector_image_rect = selector_image.getBoundingClientRect();

        // make the canvas and input steps the same size as the image
        $('#browsersteps-selector-canvas').attr('height', selector_image_rect.height).attr('width', selector_image_rect.width);
        //$('#browsersteps-selector-wrapper').attr('width', selector_image_rect.width);
        $('#browser-steps-ui').attr('width', selector_image_rect.width);

        }.debounce(10));
    });

