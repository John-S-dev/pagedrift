/**
 * Interactive Image Comparison Slider
 *
 * Allows users to drag a vertical slider to reveal differences between
 * two images (before/after comparison).
 */
(function() {
    'use strict';

    function initComparisonSlider() {
        const container = document.getElementById('comparison-container');
        const slider = document.getElementById('comparison-slider');
        const afterWrapper = container ? container.querySelector('.comparison-after') : null;
        const handle = slider ? slider.querySelector('.comparison-handle') : null;

        if (!container || !slider || !afterWrapper || !handle) {
            return;
        }

        let isDragging = false;
        let isMouseOverContainer = false;
        let mouseY = 0;

        /**
         * Update handle position - follows mouse if hovering, or viewport center
         */
        function updateHandlePosition() {
            const containerRect = container.getBoundingClientRect();
            let handleTop;

