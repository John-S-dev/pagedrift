import asyncio
import gc
import json
import os
from urllib.parse import urlparse

from loguru import logger

from changedetectionio.content_fetchers import SCREENSHOT_MAX_HEIGHT_DEFAULT, visualselector_xpath_selectors, \
    SCREENSHOT_SIZE_STITCH_THRESHOLD, SCREENSHOT_MAX_TOTAL_HEIGHT, XPATH_ELEMENT_JS, INSTOCK_DATA_JS, FAVICON_FETCHER_JS
from changedetectionio.content_fetchers.base import Fetcher, get_playwright_bypass_csp, manage_user_agent
from changedetectionio.content_fetchers.exceptions import PageUnloadable, Non200ErrorCodeReceived, EmptyReply, ScreenshotUnavailable, \
    BrowserStepsStepException


async def capture_full_page_async(page, screenshot_format='JPEG', watch_uuid=None, lock_viewport_elements=False):
    import os
    import time

    start = time.time()
    watch_info = f"[{watch_uuid}] " if watch_uuid else ""

    setup_start = time.time()
    page_height = await page.evaluate("document.documentElement.scrollHeight")
    page_width = await page.evaluate("document.documentElement.scrollWidth")
    original_viewport = page.viewport_size
    dimensions_time = time.time() - setup_start

    logger.debug(f"{watch_info}Playwright viewport size {page.viewport_size} page height {page_height} page width {page_width} (got dimensions in {dimensions_time:.2f}s)")

    # Use an approach similar to puppeteer: set a larger viewport and take screenshots in chunks
    step_size = SCREENSHOT_SIZE_STITCH_THRESHOLD # Size that won't cause GPU to overflow
    screenshot_chunks = []
    y = 0
    elements_locked = False

    # Only lock viewport elements if explicitly enabled (for image_ssim_diff processor)
    # This prevents headers/ads from resizing when viewport changes
    if lock_viewport_elements and page_height > page.viewport_size['height']:
        lock_start = time.time()
        lock_elements_js_path = os.path.join(os.path.dirname(__file__), 'res', 'lock-elements-sizing.js')
        with open(lock_elements_js_path, 'r') as f:
            lock_elements_js = f.read()
        await page.evaluate(lock_elements_js)
        elements_locked = True
        lock_time = time.time() - lock_start
        logger.debug(f"{watch_info}Viewport element locking enabled (took {lock_time:.2f}s)")

    if page_height > page.viewport_size['height']:
        if page_height < step_size:
            step_size = page_height # Incase page is bigger than default viewport but smaller than proposed step size
        # Never set viewport taller than our max capture height - otherwise one screenshot chunk
        # captures the whole (e.g. 8098px) page even when SCREENSHOT_MAX_HEIGHT=1000
        step_size = min(step_size, SCREENSHOT_MAX_TOTAL_HEIGHT)
        viewport_start = time.time()
        logger.debug(f"{watch_info}Setting bigger viewport to step through large page width W{page.viewport_size['width']}xH{step_size} because page_height > viewport_size")
        # Set viewport to a larger size to capture more content at once
        await page.set_viewport_size({'width': page.viewport_size['width'], 'height': step_size})
        viewport_time = time.time() - viewport_start
        logger.debug(f"{watch_info}Viewport changed to {page.viewport_size['width']}x{step_size} (took {viewport_time:.2f}s)")

    # Capture screenshots in chunks up to the max total height
    capture_start = time.time()
    chunk_times = []
    # Use PNG for better quality (no compression artifacts), JPEG for smaller size
    screenshot_type = screenshot_format.lower() if screenshot_format else 'jpeg'
    # PNG should use quality 100, JPEG uses configurable quality
    screenshot_quality = 100 if screenshot_type == 'png' else int(os.getenv("SCREENSHOT_QUALITY", 72))

    while y < min(page_height, SCREENSHOT_MAX_TOTAL_HEIGHT):
        # Only scroll if not at the top (y > 0)
        if y > 0:
            await page.evaluate(f"window.scrollTo(0, {y})")

