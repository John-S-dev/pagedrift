#!/usr/bin/env python3

import time
from flask import url_for
from .util import live_server_setup, wait_for_all_checks, delete_all_watches
import os

def set_multiline_response(datastore_path):
    test_return_data = """<html>
       <body>
     
     <p>Something <br>
        across 6 billion multiple<br>
        lines
     </p>
     
     <div>aaand something lines</div>
     <br>
     <div>and this should be</div>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)

    return None


