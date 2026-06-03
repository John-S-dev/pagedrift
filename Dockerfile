# pip dependencies install stage

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

# See `cryptography` pin comment in requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    gcc \
    libc-dev \
    libffi-dev \
    libjpeg-dev \
    libssl-dev \
    libxslt-dev \
    make \
    patch \
    pkg-config \
    zlib1g-dev

RUN mkdir /install
WORKDIR /install

COPY requirements.txt /requirements.txt

# Starting wrapper
COPY changedetection.py /app/changedetection.py

# Github Action test purpose(test-only.yml).
# On production, it is effectively LOGGER_LEVEL=''.
ARG LOGGER_LEVEL=''
ENV LOGGER_LEVEL="$LOGGER_LEVEL"

# Default
ENV LC_ALL=en_US.UTF-8

WORKDIR /app

# Copy and set up entrypoint script for installing extra packages
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Set entrypoint to handle EXTRA_PACKAGES env var
ENTRYPOINT ["/docker-entrypoint.sh"]

# Default command (can be overridden in docker-compose.yml)
CMD ["python", "./changedetection.py", "-d", "/datastore"]


