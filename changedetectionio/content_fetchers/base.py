import os
from abc import abstractmethod
from loguru import logger
from pydantic import BaseModel

from changedetectionio.content_fetchers import BrowserStepsStepException
from changedetectionio.strtobool import strtobool


def manage_user_agent(headers, current_ua=''):
    """
    Basic setting of user-agent

    NOTE!!!!!! The service that does the actual Chrome fetching should handle any anti-robot techniques
    THERE ARE MANY WAYS THAT IT CAN BE DETECTED AS A ROBOT!!
    This does not take care of
    - Scraping of 'navigator' (platform, productSub, vendor, oscpu etc etc) browser object (navigator.appVersion) etc
    - TCP/IP fingerprint JA3 etc
    - Graphic rendering fingerprinting
    - Your IP being obviously in a pool of bad actors
    - Too many requests
    - Scraping of SCH-UA browser replies (thanks google!!)
    - Scraping of ServiceWorker, new window calls etc

    See https://filipvitas.medium.com/how-to-set-user-agent-header-with-puppeteer-js-and-not-fail-28c7a02165da
    Puppeteer requests https://github.com/dgtlmoon/pyppeteerstealth

    :param page:
    :param headers:
    :return:
    """
    # Ask it what the user agent is, if its obviously ChromeHeadless, switch it to the default
    ua_in_custom_headers = headers.get('User-Agent')
    if ua_in_custom_headers:
        return ua_in_custom_headers

    if not ua_in_custom_headers and current_ua:
        current_ua = current_ua.replace('HeadlessChrome', 'Chrome')
        return current_ua

    return None

