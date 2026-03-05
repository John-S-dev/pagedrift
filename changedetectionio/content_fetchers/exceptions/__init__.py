from loguru import logger

class Non200ErrorCodeReceived(Exception):
    def __init__(self, status_code, url, screenshot=None, xpath_data=None, page_html=None):
        # Set this so we can use it in other parts of the app
        self.status_code = status_code
        self.url = url
        self.screenshot = screenshot
        self.xpath_data = xpath_data
        self.page_text = None

        if page_html:
            from changedetectionio import html_tools
            self.page_text = html_tools.html_to_text(page_html)
        return


class checksumFromPreviousCheckWasTheSame(Exception):
    def __init__(self):
        return


class EmptyReply(Exception):
    def __init__(self, status_code, url, screenshot=None):
        # Set this so we can use it in other parts of the app
        self.status_code = status_code
        self.url = url
        self.screenshot = screenshot
        return


class ScreenshotUnavailable(Exception):
    def __init__(self, status_code, url, page_html=None):
        # Set this so we can use it in other parts of the app
        self.status_code = status_code
        self.url = url
        if page_html:
            from changedetectionio.html_tools import html_to_text
            self.page_text = html_to_text(page_html)
        return


class ReplyWithContentButNoText(Exception):
    def __init__(self, status_code, url, screenshot=None, has_filters=False, html_content='', xpath_data=None):
        # Set this so we can use it in other parts of the app
        self.status_code = status_code
        self.url = url
        self.screenshot = screenshot
        self.has_filters = has_filters
        self.html_content = html_content
        self.xpath_data = xpath_data
        return
