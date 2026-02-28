#!/bin/bash

# exit when any command fails
set -e
# enable debug
set -x

# Test proxy list handling, starting two squids on different ports
# Each squid adds a different header to the response, which is the main thing we test for.
docker run --network changedet-network -d --name squid-one --hostname squid-one --rm -v `pwd`/tests/proxy_list/squid.conf:/etc/squid/conf.d/debian.conf ubuntu/squid:4.13-21.10_edge
docker run --network changedet-network -d --name squid-two --hostname squid-two --rm -v `pwd`/tests/proxy_list/squid.conf:/etc/squid/conf.d/debian.conf ubuntu/squid:4.13-21.10_edge

# Used for configuring a custom proxy URL via the UI - with username+password auth
docker run --network changedet-network -d \
  --name squid-custom \
  --hostname squid-custom \
  --rm \
  -v `pwd`/tests/proxy_list/squid-auth.conf:/etc/squid/conf.d/debian.conf \
  -v `pwd`/tests/proxy_list/squid-passwords.txt:/etc/squid3/passwords \
  ubuntu/squid:4.13-21.10_edge

sleep 5
## 2nd test actually choose the preferred proxy from proxies.json
# This will force a request via "proxy-two"
docker run --network changedet-network \
  -v `pwd`/tests/proxy_list/proxies.json-example:/tmp/proxies.json \
  test-changedetectionio \
  bash -c 'cd changedetectionio && pytest -s tests/proxy_list/test_multiple_proxy.py --datastore-path /tmp'

