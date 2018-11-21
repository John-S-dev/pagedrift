/**
 * Lock Element Dimensions for Screenshot Capture (First Viewport Only)
 *
 * THE PROBLEM:
 * When taking full-page screenshots of tall pages, Chrome/Puppeteer/Playwright need to:
 * 1. Temporarily change the viewport height to a large value (e.g., 800px → 3809px)
 * 2. Take screenshots in chunks while scrolling
 * 3. Stitch the chunks together
 *
 * However, changing the viewport height triggers CSS media queries like:
 *   @media (min-height: 860px) { .ad { height: 250px; } }
 *
 * This causes elements (especially ads/headers) to resize during screenshot capture.
 *
 * THE SOLUTION:
 * Lock element dimensions in the FIRST VIEWPORT ONLY with !important inline styles.
 * This prevents headers, navigation, and top ads from resizing when viewport changes.
 * We only lock the visible portion because:
 * - Most layout shifts happen in headers/navbars/top ads
 * - Locking only visible elements is 100x+ faster (100-200 elements vs 10,000+)
 * - Below-fold content shifts don't affect visual comparison accuracy
 *
 * WHAT THIS SCRIPT DOES:
 * 1. Gets current viewport height
 * 2. Finds elements within first viewport (top of page to bottom of screen)
 * 3. Locks their dimensions with !important inline styles
 * 4. Disables ResizeObserver API (for JS-based resizing)
 *
 * USAGE:
 * Execute this script BEFORE calling capture_full_page() / screenshot functions.
 * Only enabled for image_ssim_diff processor (visual comparison).
 * Default: OFF for performance.
 *
 * PERFORMANCE:
 * - Only processes 100-300 elements (first viewport) vs 10,000+ (entire page)
 * - Typically completes in 10-50ms
 * - 100x+ faster than locking entire page
 *
 * @see https://github.com/dgtlmoon/changedetection.io/issues/XXXX
 */

(() => {
    // Store original styles in a global WeakMap for later restoration
    window.__elementSizingRestore = new WeakMap();

    const start = performance.now();

    // Get current viewport height (visible portion of page)
    const viewportHeight = window.innerHeight;

    // Get all elements and filter to FIRST VIEWPORT ONLY
    // This dramatically reduces elements to process (100-300 vs 10,000+)
    const allElements = Array.from(document.querySelectorAll('*'));

    // BATCH READ PHASE: Get bounding rects and filter to viewport
    const measurements = allElements.map(el => {
        const rect = el.getBoundingClientRect();
        const computed = window.getComputedStyle(el);

        // Only lock elements in the first viewport (visible on initial page load)
        // rect.top < viewportHeight means element starts within visible area
        const inViewport = rect.top < viewportHeight && rect.top >= 0;
        const hasSize = rect.height > 0 && rect.width > 0;

