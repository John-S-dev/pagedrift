#!/usr/bin/env python3

import time
import os

from flask import url_for

from ..html_tools import *
from .util import live_server_setup, wait_for_all_checks, delete_all_watches




def set_original_response(datastore_path):
    test_return_data = """<html>
    <header>
    <h2>Header</h2>
    </header>
    <nav>
    <ul>
      <li><a href="#">A</a></li>
      <li><a href="#">B</a></li>
      <li><a href="#">C</a></li>
    </ul>
    </nav>
       <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
    <div id="changetext">Some text that will change</div>
     </body>
    <footer>
    <p>Footer</p>
    </footer>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)


def set_modified_response(datastore_path):
    test_return_data = """<html>
    <header>
    <h2>Header changed</h2>
    </header>
    <nav>
    <ul>
      <li><a href="#">A changed</a></li>
      <li><a href="#">B</a></li>
      <li><a href="#">C</a></li>
    </ul>
    </nav>
       <body>
     Some initial text<br>
     <p>Which is across multiple lines</p>
     <br>
     So let's see what happens.  <br>
    <div id="changetext">Some text that changes</div>
     </body>
    <footer>
    <p>Footer changed</p>
    </footer>
     </html>
    """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)


def test_element_removal_output():
    from inscriptis import get_text

    # Check text with sub-parts renders correctly
    content = """<html>
    <header>
    <h2>Header</h2>
    </header>
    <nav>
    <ul>
      <li><a href="#">A</a></li>
    </ul>
    </nav>
       <body>
     Some initial text<br>
     <p>across multiple lines</p>
     <div id="changetext">Some text that changes</div>
     <div>Some text should be matched by xPath // selector</div>
     <div>Some text should be matched by xPath selector</div>
     <div>Some text should be matched by xPath1 selector</div>
     </body>
    <footer>
    <p>Footer</p>
    </footer>
     </html>
    """
    html_blob = element_removal(
      [
        "header",
        "footer",
        "nav",
        "#changetext",
        "//*[contains(text(), 'xPath // selector')]",
        "xpath://*[contains(text(), 'xPath selector')]",
        "xpath1://*[contains(text(), 'xPath1 selector')]"
      ],
      html_content=content
    )
    text = get_text(html_blob)
    assert (
        text
        == """Some initial text

across multiple lines
"""
    )


