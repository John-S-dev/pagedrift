#!/usr/bin/env python3

import time
import os

from flask import url_for

from ..html_tools import *
from .util import live_server_setup, wait_for_all_checks, delete_all_watches




def set_response_with_multiple_index(datastore_path):
    data= """<!DOCTYPE html>
<html>
<body>

<!-- NOTE!! CHROME WILL ADD TBODY HERE IF ITS NOT THERE!! -->
<table style="width:100%">
  <tr>
    <th>Person 1</th>
    <th>Person 2</th>
    <th>Person 3</th>
  </tr>
  <tr>
    <td>Emil</td>
    <td>Tobias</td>
    <td>Linus</td>
  </tr>
  <tr>
    <td>16</td>
    <td>14</td>
    <td>10</td>
  </tr>
</table>
</body>
</html>
"""
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(data)


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


# Re PR #978: subtractive_selectors must run BEFORE include_filters so that selectors
# relying on ancestor context (e.g. ".main .ad") can still match. If include runs first,
# the ancestor wrapper is stripped and the subtractive selector matches nothing.
def test_subtractive_selectors_applied_before_include_filters(client, live_server, measure_memory_usage, datastore_path):
    page_html = """<html><body>
<div class="main">
  <p class="keep">first kept paragraph</p>
  <p class="advertisement">noisy advertisement text</p>
  <p class="keep">second kept paragraph</p>
</div>
</body></html>
"""
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(page_html)

    test_url = url_for("test_endpoint", _external=True)
    client.application.config.get('DATASTORE').add_watch(
        url=test_url,
        extras={
            # Include filter strips the .main wrapper from the output
            "include_filters": [".main p"],
            # Subtractive selector depends on the .main ancestor — only effective if it runs first
            "subtractive_selectors": [".main .advertisement"],
        },
    )
    client.post(url_for("ui.form_watch_checknow"), follow_redirects=True)
    wait_for_all_checks(client)

    res = client.get(
        url_for("ui.ui_preview.preview_page", uuid="first"),
        follow_redirects=True,
    )

    assert b"first kept paragraph" in res.data
    assert b"second kept paragraph" in res.data
    # The bug: ad survives if include filter runs first
    assert b"noisy advertisement text" not in res.data
