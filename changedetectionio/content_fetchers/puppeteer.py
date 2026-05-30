import asyncio
import gc
import json
import os
import websockets.exceptions
from urllib.parse import urlparse

from loguru import logger

from changedetectionio.content_fetchers import SCREENSHOT_MAX_HEIGHT_DEFAULT, visualselector_xpath_selectors, \
    SCREENSHOT_SIZE_STITCH_THRESHOLD, SCREENSHOT_DEFAULT_QUALITY, XPATH_ELEMENT_JS, INSTOCK_DATA_JS, \
    SCREENSHOT_MAX_TOTAL_HEIGHT, FAVICON_FETCHER_JS
from changedetectionio.content_fetchers.base import Fetcher, get_playwright_bypass_csp, manage_user_agent
from changedetectionio.content_fetchers.exceptions import PageUnloadable, Non200ErrorCodeReceived, EmptyReply, BrowserFetchTimedOut, \
    BrowserConnectError


async def _configure_puppeteer_csp(page):
    """Enable CSP bypass without requiring unsupported CDP methods when disabled."""
    if get_playwright_bypass_csp():
        await page.setBypassCSP(True)


# Bug 3 in Playwright screenshot handling
# Some bug where it gives the wrong screenshot size, but making a request with the clip set first seems to solve it

# Screenshots also travel via the ws:// (websocket) meaning that the binary data is base64 encoded
# which will significantly increase the IO size between the server and client, it's recommended to use the lowest
# acceptable screenshot quality here
async def capture_full_page(page, screenshot_format='JPEG', watch_uuid=None, lock_viewport_elements=False):
    import os
    import time

    start = time.time()
    watch_info = f"[{watch_uuid}] " if watch_uuid else ""

    setup_start = time.time()
    page_height = await page.evaluate("document.documentElement.scrollHeight")
    page_width = await page.evaluate("document.documentElement.scrollWidth")
    original_viewport = page.viewport
    dimensions_time = time.time() - setup_start

    logger.debug(f"{watch_info}Puppeteer viewport size {page.viewport} page height {page_height} page width {page_width} (got dimensions in {dimensions_time:.2f}s)")

    # Bug 3 in Playwright screenshot handling
    # Some bug where it gives the wrong screenshot size, but making a request with the clip set first seems to solve it
    # JPEG is better here because the screenshots can be very very large

    # Screenshots also travel via the ws:// (websocket) meaning that the binary data is base64 encoded
    # which will significantly increase the IO size between the server and client, it's recommended to use the lowest
    # acceptable screenshot quality here

    # Use PNG for better quality (no compression artifacts), JPEG for smaller size
    screenshot_type = screenshot_format.lower() if screenshot_format else 'jpeg'
    # PNG should use quality 100, JPEG uses configurable quality
    screenshot_quality = 100 if screenshot_type == 'png' else int(os.getenv("SCREENSHOT_QUALITY", 72))

    step_size = SCREENSHOT_SIZE_STITCH_THRESHOLD # Something that will not cause the GPU to overflow when taking the screenshot
    screenshot_chunks = []
    y = 0
    elements_locked = False

    # Only lock viewport elements if explicitly enabled (for image_ssim_diff processor)
    # This prevents headers/ads from resizing when viewport changes
    if lock_viewport_elements and page_height > page.viewport['height']:
        lock_start = time.time()
        lock_elements_js_path = os.path.join(os.path.dirname(__file__), 'res', 'lock-elements-sizing.js')
        file_read_start = time.time()
        with open(lock_elements_js_path, 'r') as f:
            lock_elements_js = f.read()
        file_read_time = time.time() - file_read_start

        evaluate_start = time.time()
        await page.evaluate(lock_elements_js)
        evaluate_time = time.time() - evaluate_start

        elements_locked = True
        lock_time = time.time() - lock_start
        logger.debug(f"{watch_info}Viewport element locking enabled - File read: {file_read_time:.3f}s, Browser evaluate: {evaluate_time:.2f}s, Total: {lock_time:.2f}s")

    if page_height > page.viewport['height']:
        if page_height < step_size:
            step_size = page_height # Incase page is bigger than default viewport but smaller than proposed step size
        # Never set viewport taller than our max capture height - otherwise one screenshot chunk
        # captures the whole page even when SCREENSHOT_MAX_HEIGHT is set smaller
        step_size = min(step_size, SCREENSHOT_MAX_TOTAL_HEIGHT)
        viewport_start = time.time()
        await page.setViewport({'width': page.viewport['width'], 'height': step_size})
        viewport_time = time.time() - viewport_start
        logger.debug(f"{watch_info}Viewport changed to {page.viewport['width']}x{step_size} (took {viewport_time:.2f}s)")

    capture_start = time.time()
    chunk_times = []
    while y < min(page_height, SCREENSHOT_MAX_TOTAL_HEIGHT):
        # better than scrollTo incase they override it in the page
        await page.evaluate(
            """(y) => {
                const el = document.scrollingElement;
                if (el) el.scrollTop = y;
            }""",
            y
        )

        screenshot_kwargs = {
            'type_': screenshot_type,
            'fullPage': False
        }
        # PNG doesn't support quality parameter in Puppeteer
        if screenshot_type == 'jpeg':
            screenshot_kwargs['quality'] = screenshot_quality

        chunk_start = time.time()
        screenshot_chunks.append(await page.screenshot(**screenshot_kwargs))
        chunk_time = time.time() - chunk_start
        chunk_times.append(chunk_time)
        logger.debug(f"{watch_info}Chunk {len(screenshot_chunks)} captured in {chunk_time:.2f}s")
        y += step_size

    await page.setViewport({'width': original_viewport['width'], 'height': original_viewport['height']})

    # Unlock element dimensions if they were locked
    if elements_locked:
        unlock_elements_js_path = os.path.join(os.path.dirname(__file__), 'res', 'unlock-elements-sizing.js')
        with open(unlock_elements_js_path, 'r') as f:
            unlock_elements_js = f.read()
        await page.evaluate(unlock_elements_js)
        logger.debug(f"{watch_info}Element dimensions unlocked after screenshot capture")

    capture_time = time.time() - capture_start
    total_capture_time = sum(chunk_times)
    logger.debug(f"{watch_info}All {len(screenshot_chunks)} chunks captured in {capture_time:.2f}s (total chunk time: {total_capture_time:.2f}s)")

    if len(screenshot_chunks) > 1:
        stitch_start = time.time()
        logger.debug(f"{watch_info}Starting stitching of {len(screenshot_chunks)} chunks")

        # Always use spawn subprocess for ANY stitching (2+ chunks)
        # PIL allocates at C level and Python GC never releases it - subprocess exit forces OS to reclaim
        # Trade-off: 35MB resource_tracker vs 500MB+ PIL leak in main process
        from changedetectionio.content_fetchers.screenshot_handler import stitch_images_worker_raw_bytes
        import multiprocessing
        import struct

        ctx = multiprocessing.get_context('spawn')
        parent_conn, child_conn = ctx.Pipe()
        p = ctx.Process(target=stitch_images_worker_raw_bytes, args=(child_conn, page_height, SCREENSHOT_MAX_TOTAL_HEIGHT))
        p.start()

        # Send via raw bytes (no pickle)
        parent_conn.send_bytes(struct.pack('I', len(screenshot_chunks)))
        for chunk in screenshot_chunks:
            parent_conn.send_bytes(chunk)

        screenshot = parent_conn.recv_bytes()
        p.join()

        parent_conn.close()
        child_conn.close()
        del p, parent_conn, child_conn

        stitch_time = time.time() - stitch_start
        total_time = time.time() - start
        setup_time = total_time - capture_time - stitch_time
        logger.debug(
            f"{watch_info}Screenshot complete - Page height: {page_height}px, Capture height: {SCREENSHOT_MAX_TOTAL_HEIGHT}px | "
            f"Setup: {setup_time:.2f}s, Capture: {capture_time:.2f}s, Stitching: {stitch_time:.2f}s, Total: {total_time:.2f}s")
        return screenshot

    total_time = time.time() - start
    setup_time = total_time - capture_time
    logger.debug(
        f"{watch_info}Screenshot complete - Page height: {page_height}px, Capture height: {SCREENSHOT_MAX_TOTAL_HEIGHT}px | "
        f"Setup: {setup_time:.2f}s, Single chunk: {capture_time:.2f}s, Total: {total_time:.2f}s")
    return screenshot_chunks[0]


class fetcher(Fetcher):
    fetcher_description = "Puppeteer/direct {}/Javascript".format(
        os.getenv("PLAYWRIGHT_BROWSER_TYPE", 'chromium').capitalize()
    )
    if os.getenv("PLAYWRIGHT_DRIVER_URL"):
        fetcher_description += " via '{}'".format(os.getenv("PLAYWRIGHT_DRIVER_URL"))

    browser = None
    browser_type = ''
    command_executor = ''
    proxy = None

    # Capability flags
    supports_browser_steps = True
    supports_screenshots = True
    supports_xpath_element_data = True

    @classmethod
    def get_status_icon_data(cls):
        """Return Chrome browser icon data for Puppeteer fetcher."""
        return {
            'filename': 'google-chrome-icon.png',
            'alt': 'Using a Chrome browser',
            'title': 'Using a Chrome browser'
        }

    def __init__(self, proxy_override=None, custom_browser_connection_url=None, **kwargs):
        super().__init__(**kwargs)

        # Renderer crashes recorded during the fetch, see the 'error' handler in fetch_page().
        # Set up here so run()'s finally can always report, even if we never got as far as a page.
        self.page_errors = []

        if custom_browser_connection_url:
            self.browser_connection_is_custom = True
            self.browser_connection_url = custom_browser_connection_url
        else:
            # Fallback to fetching from system
            # .strip('"') is going to save someone a lot of time when they accidently wrap the env value
            self.browser_connection_url = os.getenv("PLAYWRIGHT_DRIVER_URL", 'ws://playwright-chrome:3000').strip('"')

        # allow per-watch proxy selection override
        # @todo check global too?
        if proxy_override:
            # Playwright needs separate username and password values
            parsed = urlparse(proxy_override)
            if parsed:
                self.proxy = {'username': parsed.username, 'password': parsed.password}
                # Add the proxy server chrome start option, the username and password never gets added here
                # (It always goes in via await self.page.authenticate(self.proxy))

                # @todo filter some injection attack?
                # check scheme when no scheme
                proxy_url = parsed.scheme + "://" if parsed.scheme else 'http://'
                r = "?" if not '?' in self.browser_connection_url else '&'
                port = ":"+str(parsed.port) if parsed.port else ''
                q = "?"+parsed.query if parsed.query else ''
                proxy_url += f"{parsed.hostname}{port}{parsed.path}{q}"
                self.browser_connection_url += f"{r}--proxy-server={proxy_url}"

    async def quit(self, watch=None):
        watch_uuid = watch.get('uuid') if watch else 'unknown'

        # Close page
        try:
            if hasattr(self, 'page') and self.page:
                await asyncio.wait_for(self.page.close(), timeout=5.0)
                logger.debug(f"[{watch_uuid}] Page closed successfully")
        except asyncio.TimeoutError:
            logger.warning(f"[{watch_uuid}] Timed out closing page (5s)")
        except Exception as e:
            logger.warning(f"[{watch_uuid}] Error closing page: {e}")
        finally:
            self.page = None

        # Close browser connection
        try:
            if hasattr(self, 'browser') and self.browser:
                await asyncio.wait_for(self.browser.close(), timeout=5.0)
                logger.debug(f"[{watch_uuid}] Browser closed successfully")
        except asyncio.TimeoutError:
            logger.warning(f"[{watch_uuid}] Timed out closing browser (5s)")
        except Exception as e:
            logger.warning(f"[{watch_uuid}] Error closing browser: {e}")
        finally:
            self.browser = None

        logger.info(f"[{watch_uuid}] Cleanup puppeteer complete")

        # Force garbage collection to release resources
        gc.collect()

    async def fetch_page(self,
                         current_include_filters,
                         empty_pages_are_a_change,
                         fetch_favicon,
                         ignore_status_codes,
                         is_binary,
                         request_body,
                         request_headers,
                         request_method,
                         screenshot_format,
                         timeout,
                         url,
                         watch_uuid
                         ):
        import re
        self.delete_browser_steps_screenshots()

        n = int(os.getenv("WEBDRIVER_DELAY_BEFORE_CONTENT_READY", 12)) + self.render_extract_delay
        extra_wait = min(n, 15)

        logger.debug(f"Extra wait set to {extra_wait}s, requested was {n}s.")

        from pyppeteer import Pyppeteer
        pyppeteer_instance = Pyppeteer()

        # Connect directly using the specified browser_ws_endpoint
        # @todo timeout
        try:
            logger.debug(f"[{watch_uuid}] Connecting to browser at {self.browser_connection_url}")
            self.browser = await pyppeteer_instance.connect(browserWSEndpoint=self.browser_connection_url,
                                                            ignoreHTTPSErrors=True
                                                            )
            logger.debug(f"[{watch_uuid}] Browser connected successfully")
        except websockets.exceptions.InvalidStatusCode as e:
            raise BrowserConnectError(msg=f"Error while trying to connect the browser, Code {e.status_code} (check your access, whitelist IP, password etc)")
        except websockets.exceptions.InvalidURI:
            raise BrowserConnectError(msg=f"Error connecting to the browser, check your browser connection address (should be ws:// or wss://")
        except Exception as e:
            raise BrowserConnectError(msg=f"Error connecting to the browser - Exception '{str(e)}'")

# Plugin registration for built-in fetcher
class PuppeteerFetcherPlugin:
    """Plugin class that registers the Puppeteer fetcher as a built-in plugin."""

    def register_content_fetcher(self):
        """Register the Puppeteer fetcher"""
        return ('html_webdriver', fetcher)


