#!/usr/bin/env python3

# Read more https://github.com/dgtlmoon/changedetection.io/wiki
# Semver means never use .01, or 00. Should be .1.
__version__ = '0.60.4'

from changedetectionio.strtobool import strtobool
from json.decoder import JSONDecodeError

from loguru import logger
import getopt
import logging
import os
import platform
import signal
import threading
import time

# Limit glibc malloc arena count to prevent RSS growth from concurrent requests.
# Default: glibc creates up to 8×CPU_cores arenas. Each concurrent thread/connection
# can trigger a new arena, and freed memory stays mapped in those arenas as RSS forever.
# With MALLOC_ARENA_MAX=2, at most 2 arenas are used; freed pages return to the OS faster.
# Must be set before worker threads start; env var is read lazily by glibc on first arena creation.
if 'MALLOC_ARENA_MAX' not in os.environ:
    os.environ['MALLOC_ARENA_MAX'] = '2'
    try:
        import ctypes as _ctypes
        _ctypes.CDLL('libc.so.6').mallopt(-8, 2)  # M_ARENA_MAX = -8
    except Exception:
        pass

