import sys
import os
import pytest

from changedetectionio import html_tools

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# test generation guide.
# 1. Do not include encoding in the xml declaration if the test object is a str type.
# 2. Always paraphrase test.

hotels = """
<hotel>
  <branch location="California">
    <staff>
      <given_name>Christopher</given_name>
      <surname>Anderson</surname>
      <age>25</age>
    </staff>
    <staff>
      <given_name>Christopher</given_name>
      <surname>Carter</surname>
      <age>30</age>
    </staff>
  </branch>
  <branch location="Las Vegas">
    <staff>
      <given_name>Lisa</given_name>
      <surname>Walker</surname>
      <age>60</age>
    </staff>
    <staff>
      <given_name>Jessica</given_name>
      <surname>Walker</surname>
      <age>32</age>
    </staff>
    <staff>
      <given_name>Jennifer</given_name>
      <surname>Roberts</surname>
      <age>50</age>
    </staff>
  </branch>
</hotel>"""

