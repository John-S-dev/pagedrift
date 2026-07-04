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

        x_scale = selector_image_rect.width / xpath_data['browser_width'];
        y_scale = selector_image_rect.height / selector_image.naturalHeight;
        ctx.strokeStyle = 'rgba(255,0,0, 0.9)';
        ctx.fillStyle = 'rgba(255,0,0, 0.1)';
        ctx.lineWidth = 3;
        console.log("scaling set  x: " + x_scale + " by y:" + y_scale);
    }

    // bootstrap it, this will trigger everything else
    $('#browsersteps-img').bind('load', function () {
        $('body').addClass('full-width');
        console.log(`Loaded background ${this.naturalWidth}px` );
        // For the UI width of the whole edit area
        document.documentElement.style.setProperty('--browser-steps-max-width', `${this.naturalWidth+200}px` );

        document.getElementById("browsersteps-selector-canvas");
        c = document.getElementById("browsersteps-selector-canvas");
        // redline highlight context
        ctx = c.getContext("2d");
        // @todo is click better?
        $('#browsersteps-selector-canvas').off("mousemove mousedown click");
        // Undo disable_browsersteps_ui
        $("#browser-steps-ui").css('opacity', '1.0');

        // init
        set_scale();

        // @todo click ? some better library?
        $('#browsersteps-selector-canvas').bind('click', function (e) {
            // https://developer.mozilla.org/en-US/docs/Web/API/MouseEvent
            e.preventDefault()
        });

        // When the mouse moves we know which element it should be above
        // mousedown will link that to the UI (select the right action, highlight etc)
        $('#browsersteps-selector-canvas').bind('mousedown', function (e) {
            // https://developer.mozilla.org/en-US/docs/Web/API/MouseEvent
            e.preventDefault()
            last_click_xy = {'x': parseInt((1 / x_scale) * e.offsetX), 'y': parseInt((1 / y_scale) * e.offsetY)}
            process_selected(current_selected_i);
            current_selected_i = false;

            // if process selected returned false, then best we can do is offer a x,y click :(
            if (!found_something) {
                var first_available = $("ul#browser_steps li.empty").first();
                $('select', first_available).val('Click X,Y').change();
                $('input[type=text]', first_available).first().val(last_click_xy['x'] + ',' + last_click_xy['y']);
                draw_circle_on_canvas(e.offsetX, e.offsetY);
            }
        });

        // Debounce and find the current most 'interesting' element we are hovering above
        $('#browsersteps-selector-canvas').bind('mousemove', function (e) {
            if (!xpath_data) {
                return;
            }

            // checkbox if find elements is enabled
            ctx.clearRect(0, 0, c.width, c.height);
            ctx.fillStyle = 'rgba(255,0,0, 0.1)';
            ctx.strokeStyle = 'rgba(255,0,0, 0.9)';

            // Add in offset
            if ((typeof e.offsetX === "undefined" || typeof e.offsetY === "undefined") || (e.offsetX === 0 && e.offsetY === 0)) {
                var targetOffset = $(e.target).offset();
                e.offsetX = e.pageX - targetOffset.left;
                e.offsetY = e.pageY - targetOffset.top;
            }
            current_selected_i = false;
            // Reverse order - the most specific one should be deeper/"laster"
            // Basically, find the most 'deepest'
            var possible_elements = [];
            xpath_data['size_pos'].forEach(function (item, index) {
                // If we are in a bounding-box
                if (e.offsetY > item.top * y_scale && e.offsetY < item.top * y_scale + item.height * y_scale
                    &&
                    e.offsetX > item.left * y_scale && e.offsetX < item.left * y_scale + item.width * y_scale

                ) {
                    // Ignore really large ones, because we are scraping 'div' also from xpath_element_scraper but
                    // that div or whatever could be some wrapper and would generally make you select the whole page
                    if (item.width > 800 && item.height > 400) {
                        return
                    }

                    // There could be many elements here, record them all and then we'll find out which is the most 'useful'
                    // (input, textarea, button, A etc)
                    if (item.width < xpath_data['browser_width']) {
                        possible_elements.push(item);
                    }
                }
            });

            // Find the best one
            if (possible_elements.length) {
                possible_elements.forEach(function (item, index) {
                  if (["a", "input", "select", "textarea", "button"].includes(item['tagName'])) {
                      current_selected_i = item;
                  }
                });

                if (!current_selected_i) {
                    current_selected_i = possible_elements[0];
                }

                sel = xpath_data['size_pos'][current_selected_i];
                ctx.strokeRect(current_selected_i.left * x_scale, current_selected_i.top * y_scale, current_selected_i.width * x_scale, current_selected_i.height * y_scale);
                ctx.fillRect(current_selected_i.left * x_scale, current_selected_i.top * y_scale, current_selected_i.width * x_scale, current_selected_i.height * y_scale);
            }


        }.debounce(10));
    });

//    $("#browser-steps-fieldlist").bind('mouseover', function(e) {
//        console.log(e.xpath_data_index);
    // });


    // callback for clicking on an xpath on the canvas
    function process_selected(selected_in_xpath_list) {
        found_something = false;
        var first_available = $("ul#browser_steps li.empty").first();


        if (selected_in_xpath_list !== false) {
            // Nothing focused, so fill in a new one
            // if inpt type button or <button>
            // from the top, find the next not used one and use it
            var x = selected_in_xpath_list;
            console.log(x);
            if (x && first_available.length) {
                // @todo will it let you click shit that has a layer ontop? probably not.
                if (x['tagtype'] === 'text' || x['tagtype'] === 'number' || x['tagtype'] === 'email' || x['tagName'] === 'textarea' || x['tagtype'] === 'password' || x['tagtype'] === 'search') {
                    $('select', first_available).val('Enter text in field').change();
                    $('input[type=text]', first_available).first().val(x['xpath']);
                    $('input[placeholder="Value"]', first_available).addClass('ok').click().focus();
                    found_something = true;
                }
                else if (x['tagName'] === 'select') {
                    $('select', first_available).val('<select> by option text').change();
                    $('input[type=text]', first_available).first().val(x['xpath']);
                    $('input[placeholder="Value"]', first_available).addClass('ok').click().focus();
                    found_something = true;
                }
                else {
                    // There's no good way (that I know) to find if this
                    // see https://stackoverflow.com/questions/446892/how-to-find-event-listeners-on-a-dom-node-in-javascript-or-in-debugging
                    // https://codepen.io/azaslavsky/pen/DEJVWv

                    // So we dont know if its really a clickable element or not :-(
                    // Assume it is - then we dont fill the pages with unreliable "Click X,Y" selections
                    // If you switch to "Click X,y" after an element here is setup, it will give the last co-ords anyway
                    //if (x['isClickable'] || x['tagName'].startsWith('h') || x['tagName'] === 'a' || x['tagName'] === 'button' || x['tagtype'] === 'submit' || x['tagtype'] === 'checkbox' || x['tagtype'] === 'radio' || x['tagtype'] === 'li') {
                        $('select', first_available).val('Click element').change();
                        $('input[type=text]', first_available).first().val(x['xpath']).focus();
                        found_something = true;
                    //}
                }
            }
        }
    }

    function draw_circle_on_canvas(x, y) {
        ctx.beginPath();
        ctx.arc(x, y, 8, 0, 2 * Math.PI, false);
        ctx.fillStyle = 'rgba(255,0,0, 0.6)';
        ctx.fill();
    }

    // Reusable AJAX function for browser step operations
    function executeBrowserStep(url, data = {}) {
        $('#browser-steps-ui .loader .spinner').fadeIn();
        apply_buttons_disabled = true;
        $('ul#browser_steps li .control .apply').css('opacity', 0.5);
        $("#browsersteps-img").css('opacity', 0.65);

        if (config[0] == 0) {
            $(elem_selector).fadeOut();
        } else {
            $(elem_selector).fadeIn();
        }
        if (config[1] == 0) {
            $(elem_value).fadeOut();
        } else {
            $(elem_value).fadeIn();
        }

        if ($(this).val() === 'Click X,Y' && last_click_xy['x'] > 0 && $(elem_value).val().length === 0) {
            // @todo handle scale
            $(elem_value).val(last_click_xy['x'] + ',' + last_click_xy['y']).focus();
        }
    }).change();

    function set_greyed_state() {
        $('ul#browser_steps select').not('option:selected[value="Choose one"]').closest('li').removeClass('empty');
        $('ul#browser_steps select option:selected[value="Choose one"]').closest('li').addClass('empty');
    }

    // Add the extra buttons to the steps
    $('ul#browser_steps li').each(function (i) {
            var s = '<div class="control">' + '<a data-step-index=' + i + ' class="pure-button button-secondary button-green button-xsmall apply" >Apply</a>&nbsp;';
            s += `<a data-step-index="${i}" class="pure-button button-secondary button-xsmall clear" >Clear</a>&nbsp;` +
                `<a data-step-index="${i}" class="pure-button button-secondary button-red button-xsmall remove" >Remove</a>`;

            // if a screenshot is available
            if (browser_steps_available_screenshots.includes(i.toString())) {
                var d = (browser_steps_last_error_step === i+1) ? 'before' : 'after';
                s += `&nbsp;<a data-step-index="${i}" class="pure-button button-secondary button-xsmall show-screenshot" title="Show screenshot from last run" data-type="${d}">Pic</a>&nbsp;`;
            }
            s += '</div>';
            $(this).append(s)
        }
    );

    $('ul#browser_steps li .control .clear').click(function (element) {
        $("select", $(this).closest('li')).val("Choose one").change();
        $(":text", $(this).closest('li')).val('');
    });


    $('ul#browser_steps li .control .remove').click(function (element) {
        // so you wanna remove the 2nd (3rd spot 0,1,2,...)
        var p = $("#browser_steps li").index($(this).closest('li'));

