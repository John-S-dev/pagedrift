# HTML to TEXT/JSON DIFFERENCE self.fetcher

import hashlib
import json
import os
import re
import urllib3

from changedetectionio.processors.magic import guess_stream_type

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

JSON_FILTER_PREFIXES = ['json:', 'jq:', 'jqraw:']

