#!/usr/bin/env python3
# coding=utf-8

"""Unit tests for html_tools.html_to_text function."""

import hashlib
import threading
import unittest
from queue import Queue

from changedetectionio.html_tools import html_to_text


