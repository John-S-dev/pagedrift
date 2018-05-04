#!/usr/bin/env python3

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

