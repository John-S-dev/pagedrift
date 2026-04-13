import os
import time
import re
from random import randint
from loguru import logger

from changedetectionio.content_fetchers import SCREENSHOT_MAX_HEIGHT_DEFAULT
from changedetectionio.content_fetchers.base import get_playwright_bypass_csp, manage_user_agent
from changedetectionio.jinja2_custom import render as jinja_render
from changedetectionio.validate_url import validate_fetch_url_async

def browser_steps_get_valid_steps(browser_steps: list):
    if browser_steps is not None and len(browser_steps):
        valid_steps = list(filter(
            lambda s: (s['operation'] and len(s['operation']) and s['operation'] != 'Choose one'),browser_steps))

        # Just incase they selected Goto site by accident with older JS
        if valid_steps and valid_steps[0]['operation'] == 'Goto site':
            del(valid_steps[0])

        return valid_steps
    return []


# Two flags, tell the JS which of the "Selector" or "Value" field should be enabled in the front end
# 0- off, 1- on
browser_step_ui_config = {'Choose one': '0 0',
                          #                 'Check checkbox': '1 0',
                          #                 'Click button containing text': '0 1',
                          #                 'Scroll to bottom': '0 0',
                          #                 'Scroll to element': '1 0',
                          #                 'Scroll to top': '0 0',
                          #                 'Switch to iFrame by index number': '0 1'
                          #                 'Uncheck checkbox': '1 0',
                          # @todo
                          'Check checkbox': '1 0',
                          'Click X,Y': '0 1',
                          'Click element if exists': '1 0',
                          'Click element': '1 0',
                          'Click element containing text': '0 1',
                          'Click element containing text if exists': '0 1',
                          'Enter text in field': '1 1',
                          'Execute JS': '0 1',
#                          'Extract text and use as filter': '1 0',
                          'Goto site': '0 0',
                          'Goto URL': '0 1',
                          'Make all child elements visible': '1 0',
                          'Press Enter': '0 0',
                          'Select by label': '1 1',
                          '<select> by option text': '1 1',
                          'Scroll down': '0 0',
                          'Uncheck checkbox': '1 0',
                          'Wait for seconds': '0 1',
                          'Wait for text': '0 1',
                          'Wait for text in element': '1 1',
                          'Remove elements': '1 0',
                          #                          'Press Page Down': '0 0',
                          #                          'Press Page Up': '0 0',
                          # weird bug, come back to it later
                          }


# Good reference - https://playwright.dev/python/docs/input
#                  https://pythonmana.com/2021/12/202112162236307035.html
#
# ONLY Works in Playwright because we need the fullscreen screenshot
class steppable_browser_interface():
    page = None
    start_url = None
    action_timeout = 10 * 1000

    def __init__(self, start_url):
        self.start_url = start_url

    # Convert and perform "Click Button" for example
    async def call_action(self, action_name, selector=None, optional_value=None):
        if self.page is None:
            logger.warning("Cannot call action on None page object")
            return
            
        now = time.time()
        call_action_name = re.sub('[^0-9a-zA-Z]+', '_', action_name.lower())
        if call_action_name == 'choose_one':
            return

        logger.debug(f"> Action calling '{call_action_name}'")
        # https://playwright.dev/python/docs/selectors#xpath-selectors
        if selector and selector.startswith('/') and not selector.startswith('//'):
            selector = "xpath=" + selector

        elem = self.page.get_by_text(value)
        count = await elem.count()
        logger.debug(f"Clicking element containing text - {count} elements found")
        if count:
            await elem.first.click(delay=randint(200, 500), timeout=self.action_timeout)
                

    async def action_enter_text_in_field(self, selector, value):
        if not selector or not len(selector.strip()):
            return

        await self.page.fill(selector, value, timeout=self.action_timeout)

    async def action_execute_js(self, selector, value):
        if not value:
            return None
            
        return await self.page.evaluate(value)

    async def action_click_element(self, selector, value):
        logger.debug("Clicking element")
        if not selector or not len(selector.strip()):
            return

        await self.page.click(selector=selector, timeout=self.action_timeout + 20 * 1000, delay=randint(200, 500))

    async def action_click_element_if_exists(self, selector, value):
        import playwright._impl._errors as _api_types
        logger.debug("Clicking element if exists")
        if not selector or not len(selector.strip()):
            return
            
        try:
            await self.page.click(selector, timeout=self.action_timeout, delay=randint(200, 500))
        except _api_types.TimeoutError:
            return
        except _api_types.Error:
            # Element was there, but page redrew and now its long long gone
            return
                

    async def action_click_x_y(self, selector, value):
        if not value or not re.match(r'^\s?\d+\s?,\s?\d+\s?$', value):
            logger.warning("'Click X,Y' step should be in the format of '100 , 90'")
            return

        try:
            x, y = value.strip().split(',')
            x = int(float(x.strip()))
            y = int(float(y.strip()))
            
            await self.page.mouse.click(x=x, y=y, delay=randint(200, 500))
                
        except Exception as e:
            logger.error(f"Error parsing x,y coordinates: {str(e)}")

    async def action__select_by_option_text(self, selector, value):
        if not selector or not len(selector.strip()):
            return

