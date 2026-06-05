// Search modal functionality
(function() {
  'use strict';

  document.addEventListener('DOMContentLoaded', function() {
    const searchModal = document.getElementById('search-modal');
    // The Search button is rendered in the left rail and the mobile drawer.
    const openSearchButtons = document.querySelectorAll('.js-open-search-modal');
    const closeSearchButton = document.getElementById('close-search-modal');
    const searchForm = document.getElementById('search-form');
    const searchInput = document.getElementById('search-modal-input');

    if (!searchModal || openSearchButtons.length === 0) {
      return;
    }

    // Open modal
    function openSearchModal() {
      searchModal.showModal();
      // Focus the input after a small delay to ensure modal is rendered
      setTimeout(function() {
        if (searchInput) {
          searchInput.focus();
        }
      }, 100);
    }

    // Close modal
    function closeSearchModal() {
      searchModal.close();
      if (searchInput) {
        searchInput.value = '';
      }
    }

    // Open search modal on button click (desktop + mobile drawer)
    openSearchButtons.forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        // Close mobile drawer if open, so the modal isn't behind it
        const drawer = document.getElementById('mobile-menu-drawer');
        const overlay = document.getElementById('mobile-menu-overlay');
        const toggle = document.getElementById('hamburger-toggle');
        if (drawer && drawer.classList.contains('active')) {
          drawer.classList.remove('active');
          if (overlay) overlay.classList.remove('active');
          if (toggle) toggle.classList.remove('active');
        }
        openSearchModal();
      });
    });

    // Close modal on cancel button
    if (closeSearchButton) {
      closeSearchButton.addEventListener('click', closeSearchModal);
    }

    // Close modal on escape key (native behavior for dialog)
    searchModal.addEventListener('cancel', function(e) {
      if (searchInput) {
        searchInput.value = '';
      }
    });

