#!/bin/bash

# run some tests and look if the 'custom-browser-search-string=1' connect string appeared in the correct containers

# @todo do it again but with the puppeteer one

# enable debug
set -x
docker network inspect changedet-network >/dev/null 2>&1 || docker network create changedet-network
docker run --network changedet-network -d --hostname selenium  -p 4444:4444 --rm --shm-size="2g"  selenium/standalone-chrome:4

