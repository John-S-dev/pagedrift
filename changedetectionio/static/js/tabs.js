// Rewrite this is a plugin.. is all this JS really 'worth it?'

window.addEventListener('hashchange', function () {
    // Only remove active from tab elements, not menu items
    var tabs = document.querySelectorAll('.tabs li.active');
    tabs.forEach(function(tab) {
        tab.classList.remove('active');
    });
    document.body.classList.remove('full-width');
    set_active_tab();
}, false);

var has_errors = document.querySelectorAll(".messages .error");
if (!has_errors.length) {
    if (document.location.hash == "") {
        location.replace(document.querySelector(".tabs ul li:first-child a").hash);
    } else {
        set_active_tab();
    }
} else {
    focus_error_tab();
}

