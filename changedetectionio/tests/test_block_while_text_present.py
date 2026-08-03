#!/usr/bin/env python3

import time
from flask import url_for
from .util import live_server_setup, wait_for_all_checks, delete_all_watches
from changedetectionio import html_tools
import os

def set_original_ignore_response(datastore_path):

    test_return_data = """<html>
       <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
     </body>
     </html>

    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)


def set_modified_original_ignore_response(datastore_path):
    test_return_data = """<html>
       <body>
     Some NEW nice initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
     <p>new ignore stuff</p>
     <p>out of stock</p>
     <p>blah</p>
     </body>
     </html>

    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)


# Is the same but includes ZZZZZ, 'ZZZZZ' is the last line in ignore_text
def set_modified_response_minus_block_text(datastore_path):
    test_return_data = """<html>
       <body>
     Some NEW nice initial text<br>
     <p>Which is across multiple lines</p>
     <p>now on sale $2/p>
     <br>
     So let's see what happens.  <br>
     <p>new ignore stuff</p>
     <p>blah</p>
     </body>
     </html>

    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)


