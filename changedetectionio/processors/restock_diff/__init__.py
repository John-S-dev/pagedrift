
from babel.numbers import parse_decimal
from changedetectionio.model.Watch import model as BaseWatch
from decimal import Decimal, InvalidOperation
from typing import Union
import re

# Processor capabilities
supports_visual_selector = True
supports_browser_steps = True
supports_text_filters_and_triggers = True
supports_text_filters_and_triggers_elements = True
supports_request_type = True
_price_re = re.compile(r"Price:\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


