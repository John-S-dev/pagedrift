import io
import os
import re
import time
import pytest

from changedetectionio.tests.util import set_modified_response
from .util import live_server_setup, wait_for_all_checks, delete_all_watches
from .. import strtobool


