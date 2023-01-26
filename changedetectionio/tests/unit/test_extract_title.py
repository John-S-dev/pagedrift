#!/usr/bin/env python3
# coding=utf-8

"""Unit tests for html_tools.extract_title — including regression for #4217.

Issue #4217: extract_title silently returns None for pages where <title> is
pushed past the hard-coded 8 192-character scan window by large <head> content
(e.g. Amazon product pages where <title> can sit at character index 55 000+).
"""

import unittest

