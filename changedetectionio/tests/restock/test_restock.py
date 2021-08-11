#!/usr/bin/env python3
import os
import time
from flask import url_for
from ..util import live_server_setup, wait_for_all_checks, extract_UUID_from_client, wait_for_notification_endpoint_output
from changedetectionio.notification import (
    default_notification_body,
    default_notification_format,
    default_notification_title,
    valid_notification_formats,
)


def set_original_response(datastore_path):
    test_return_data = """<html>
       <body>
       <section id=header style="padding: 50px; height: 350px">This is the header which should be ignored always - <span>add to cart</span></section>
       <!-- stock-not-in-stock.js will ignore text in the first 300px, see elementIsInEyeBallRange(), sometimes "add to cart" and other junk is here -->
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
     <div>price: $10.99</div>
     <div id="sametext">Out of stock</div>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None



def set_back_in_stock_response(datastore_path):
    test_return_data = """<html>
       <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
     <div>price: $10.99</div>
     <div id="sametext">Available!</div>
     </body>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)
    return None

