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


def _extract_itemprop_availability_worker(pipe_conn):
    """
    Subprocess worker for itemprop extraction (Linux memory management).

    Uses spawn multiprocessing to isolate extruct/lxml memory allocations.
    When the subprocess exits, the OS reclaims ALL memory including lxml's
    C-level allocations that Python's GC cannot release.

    Args:
        pipe_conn: Pipe connection to receive HTML and send result
    """
    import json
    import gc

    html_content = None
    result_data = None

    try:
        # Receive HTML as raw bytes (no pickle)
        html_bytes = pipe_conn.recv_bytes()
        html_content = html_bytes.decode('utf-8')

        # Explicitly delete html_bytes to free memory
        del html_bytes
        gc.collect()

        # Perform extraction in subprocess (uses extruct/lxml)
        result_data = get_itemprop_availability(html_content)

        # Convert Restock object to dict for JSON serialization
        result = {
            'success': True,
            'data': dict(result_data) if result_data else {}
        }
        pipe_conn.send_bytes(json.dumps(result).encode('utf-8'))

        # Clean up before exit
        del result_data, html_content, result
        gc.collect()

    except MoreThanOnePriceFound:
        # Serialize the specific exception type
        result = {
            'success': False,
            'exception_type': 'MoreThanOnePriceFound'
        }
        pipe_conn.send_bytes(json.dumps(result).encode('utf-8'))

    except Exception as e:
        # Serialize other exceptions
        result = {
            'success': False,
            'exception_type': type(e).__name__,
            'exception_message': str(e)
        }
        pipe_conn.send_bytes(json.dumps(result).encode('utf-8'))

    finally:
        # Final cleanup before subprocess exits
        # Variables may already be deleted in try block, so use try/except
        try:
            del html_content
        except (NameError, UnboundLocalError):
            pass
        try:
            del result_data
        except (NameError, UnboundLocalError):
            pass
        gc.collect()
        pipe_conn.close()


def is_between(number, lower=None, upper=None):
    """
    Check if a number is between two values.

    Parameters:
    number (float): The number to check.
    lower (float or None): The lower bound (inclusive). If None, no lower bound.
    upper (float or None): The upper bound (inclusive). If None, no upper bound.

    Returns:
    bool: True if the number is between the lower and upper bounds, False otherwise.
    """
    return (lower is None or lower <= number) and (upper is None or number <= upper)


