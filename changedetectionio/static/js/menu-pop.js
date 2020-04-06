// "More" overflow menu (the kebab button in the top menu). Toggles its sibling
// .menu-pop open/closed; closes on click-outside, Escape, or selecting an item.
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    const toggles = Array.prototype.slice.call(document.querySelectorAll('.js-menu-more-toggle'));
    if (!toggles.length) return;

    function closeAll() {
      document.querySelectorAll('.menu-pop.open').forEach(function (pop) {
        pop.classList.remove('open');
      });
      toggles.forEach(function (t) { t.setAttribute('aria-expanded', 'false'); });
    }

    toggles.forEach(function (toggle) {
      const pop = toggle.parentElement.querySelector('.menu-pop');
      if (!pop) return;

