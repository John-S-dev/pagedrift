"""
History/diff rendering for the restock_diff (price / stock availability) processor.

A text diff is meaningless for restock watches - each history snapshot is just a short
string like "In Stock: True - Price: 12.34". So instead of a diff, this renders the whole
timeline as a simple smoothed line graph of price over time, coloured green where the item
was in stock and red where it was out of stock.

Conforms to processors.difference_base.DifferenceRenderer (module-level render()), and also
provides an optional get_data() hook served as JSON by /diff/<uuid>/processor-data so the
(potentially long) timeline stays out of the rendered HTML - same rationale as the preview
asset endpoint.
"""
import re
import statistics
import time

from flask_babel import gettext
from loguru import logger

# Snapshot format is written by processor.py:  f"In Stock: {in_stock} - Price: {price}"
_RE_PRICE = re.compile(r"Price:\s*([\d.]+)", re.IGNORECASE)
_RE_INSTOCK = re.compile(r"In Stock:\s*(True|False)", re.IGNORECASE)


