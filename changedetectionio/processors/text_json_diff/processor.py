# HTML to TEXT/JSON DIFFERENCE self.fetcher

import hashlib
import json
import os
import re
import urllib3

from changedetectionio.processors.magic import guess_stream_type

JSON_FILTER_PREFIXES = ['json:', 'jq:', 'jqraw:']

