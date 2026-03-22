from ..base import difference_detection_processor
from ..exceptions import ProcessorException
from . import Restock
from loguru import logger
from changedetectionio.content_fetchers.exceptions import checksumFromPreviousCheckWasTheSame

import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# Translatable strings - extracted by pybabel, translated at runtime in __init__.py
# Use a marker function so pybabel can extract these strings
def _(x): return x  # Translation marker for extraction only
name = _('Re-stock & Price detection for pages with a SINGLE product')
description = _('Detects if the product goes back to in-stock')
del _  # Remove marker function
processor_weight = 1
list_badge_text = "Restock"  # _()

class UnableToExtractRestockData(Exception):
    def __init__(self, status_code):
        # Set this so we can use it in other parts of the app
        self.status_code = status_code
        return

class MoreThanOnePriceFound(Exception):
    def __init__(self):
        return

def _search_prop_by_value(matches, value):
    for properties in matches:
        for prop in properties:
            if value in prop[0]:
                return prop[1]  # Yield the desired value and exit the function

def _deduplicate_prices(data):
    import re

    '''
    Some price data has multiple entries, OR it has a single entry with ['$159', '159', 159, "$ 159"] or just "159"
    Get all the values, clean it and add it to a set then return the unique values
    '''
    unique_data = set()

    # Return the complete 'datum' where its price was not seen before
    for datum in data:

        if isinstance(datum.value, list):
            # Process each item in the list
            normalized_value = set([float(re.sub(r'[^\d.]', '', str(item))) for item in datum.value if str(item).strip()])
            unique_data.update(normalized_value)
        else:
            # Process single value
            v = float(re.sub(r'[^\d.]', '', str(datum.value)))
            unique_data.add(v)

    return list(unique_data)


