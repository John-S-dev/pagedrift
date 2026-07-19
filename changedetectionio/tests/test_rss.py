#!/usr/bin/env python3
import email.utils
import os
import time
import pytest
from flask import url_for
from .util import set_original_response, set_modified_response, live_server_setup, wait_for_all_checks, extract_rss_token_from_UI, \
    extract_UUID_from_client, delete_all_watches
from loguru import logger
from ..blueprint.rss import RSS_FORMAT_TYPES


def set_original_cdata_xml(datastore_path):
    test_return_data = """<rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:media="http://search.yahoo.com/mrss/" xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
    <channel>
    <title>Gizi</title>
    <link>https://test.com</link>
    <atom:link href="https://testsite.com" rel="self" type="application/rss+xml"/>
    <description>
    <![CDATA[ The Future Could Be Here ]]>
    </description>
    <language>en</language>
    <item>
    <title>
    <![CDATA[ <img src="https://testsite.com/hacked.jpg"> Hackers can access your computer ]]>
    </title>
    <link>https://testsite.com/news/12341234234</link>
    <description>
    <![CDATA[ <img class="type:primaryImage" src="https://testsite.com/701c981da04869e.jpg"/><p>The days of Terminator and The Matrix could be closer. But be positive.</p><p><a href="https://testsite.com">Read more link...</a></p> ]]>
    </description>
    <category>cybernetics</category>
    <category>rand corporation</category>
    <pubDate>Tue, 17 Oct 2023 15:10:00 GMT</pubDate>
    <guid isPermaLink="false">1850933241</guid>
    <dc:creator>
    <![CDATA[ Mr Hacker News ]]>
    </dc:creator>
    <media:thumbnail url="https://testsite.com/thumbnail-c224e10d81488e818701c981da04869e.jpg"/>
    </item>

    <item>
        <title>    Some other title    </title>
        <link>https://testsite.com/news/12341234236</link>
        <description>
        Some other description
        </description>
    </item>    
    </channel>
    </rss>
            """

    with open(os.path.join(datastore_path, "endpoint-content.txt"), "w") as f:
        f.write(test_return_data)



def set_html_content(datastore_path, content):
    test_return_data = f"""<html>
       <body>
     Some initial text<br>
     <p>{content}</p>
     <br>
     So let's see what happens.  <br>
     </body>
     </html>
    """

    # Write as UTF-8 encoded bytes
    with open(os.path.join(datastore_path, "endpoint-content.txt"), "wb") as f:
        f.write(test_return_data.encode('utf-8'))


