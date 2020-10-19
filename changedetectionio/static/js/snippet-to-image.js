/**
 * snippet-to-image.js
 * Converts selected diff content to a shareable JPEG image with metadata
 */

// Constants
const IMAGE_PADDING = 5;
const JPEG_QUALITY = 0.95;
const CANVAS_SCALE = 1;
const RENDER_DELAY_MS = 50;

/**
 * Utility: Get formatted current date with timezone
 */
function getFormattedDate() {
    return new Date().toLocaleString(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZoneName: 'short'
    });
}

/**
 * Utility: Get version comparison info from the diff selectors
 */
function getVersionInfo() {
    const fromSelect = document.getElementById('diff-from-version');
    const toSelect = document.getElementById('diff-to-version');

    if (!fromSelect || !toSelect) {
        return '';
    }

    const fromOption = fromSelect.options[fromSelect.selectedIndex];
    const toOption = toSelect.options[toSelect.selectedIndex];
    const fromLabel = fromOption ? (fromOption.getAttribute('label') || fromOption.text) : 'Unknown';
    const toLabel = toOption ? (toOption.getAttribute('label') || toOption.text) : 'Unknown';

    return `Change comparison from <strong>${fromLabel}</strong> to <strong>${toLabel}</strong>`;
}

