#!/bin/bash


# live_server will throw errors even with live_server_scope=function if I have the live_server setup in different functions
# and I like to restart the server for each test (and have the test cleanup after each test)
# merge request welcome :)


# exit when any command fails
set -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
rm tests/logs/* -f

# Since theres no curl installed lets roll with python3
check_sanity() {
  local port="$1"
  if [ -z "$port" ]; then
    echo "Usage: check_sanity <port>" >&2
    return 1
  fi

  python3 - "$port" <<'PYCODE'
import sys, time, urllib.request, socket

port = sys.argv[1]
url = f'http://localhost:{port}'
ok = False

