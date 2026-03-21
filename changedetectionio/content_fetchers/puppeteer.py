import asyncio
import gc
import json
import os
import websockets.exceptions
from urllib.parse import urlparse

from loguru import logger

async def _configure_puppeteer_csp(page):
    """Enable CSP bypass without requiring unsupported CDP methods when disabled."""
    if get_playwright_bypass_csp():
        await page.setBypassCSP(True)


