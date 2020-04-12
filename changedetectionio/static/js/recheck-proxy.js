$(function () {
    /* add container before each proxy location to show status */
    var isActive = false;

    function setup_html_widget() {
        var option_li = $('.fetch-backend-proxy li').filter(function () {
            return $("input", this)[0].value.length > 0;
        });
        $(option_li).prepend('<div class="proxy-status"></div>');
        $(option_li).append('<div class="proxy-timing"></div><div class="proxy-check-details"></div>');
    }

    function set_proxy_check_status(proxy_key, state) {
        // select input by value name
        const proxy_li = $('input[value="' + proxy_key + '" ]').parent();
        if (state['status'] === 'RUNNING') {
            $('.proxy-status', proxy_li).html('<span class="spinner"></span>');
        }
        if (state['status'] === 'OK') {
            $('.proxy-status', proxy_li).html('<span style="color: green; font-weight: bold" >OK</span>');
            $('.proxy-check-details', proxy_li).html(state['text']);
        }
        if (state['status'] === 'ERROR' || state['status'] === 'ERROR OTHER') {
            $('.proxy-status', proxy_li).html('<span style="color: red; font-weight: bold" >X</span>');
            $('.proxy-check-details', proxy_li).html(state['text']);
        }
        $('.proxy-timing', proxy_li).html(state['time']);
    }


    function pollServer() {
        if (isActive) {
            window.setTimeout(function () {
                $.ajax({
                    url: proxy_recheck_status_url,
                    success: function (data) {
                        var all_done = true;
                        $.each(data, function (proxy_key, state) {
                            set_proxy_check_status(proxy_key, state);
                            if (state['status'] === 'RUNNING') {
                                all_done = false;
                            }
                        });

                        if (all_done) {
                            console.log("Shutting down poller, all done.")
                            isActive = false;
                        } else {
                            pollServer();
                        }
                    },
                    error: function () {
                        //ERROR HANDLING
                        pollServer();
                    }
                });
            }, 2000);
        }
    }

    $('#check-all-proxies').click(function (e) {

