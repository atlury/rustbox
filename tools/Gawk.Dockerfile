ARG BASE_IMAGE=rustbox-findutils:2026-11-22
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Build the complete canonical GNU Gawk feature set.  MPFR supplies -M
# arbitrary-precision arithmetic; libsigsegv exercises the canonical stack
# overflow handling instead of silently compiling a reduced oracle.
RUN apt-get update \
 && apt-get install -y --reinstall --no-install-recommends mawk \
 && apt-get install -y --no-install-recommends \
      libmpfr-dev libsigsegv-dev \
 && file /usr/bin/mawk | grep -q 'ELF 64-bit' \
 && /usr/bin/mawk 'BEGIN { exit 0 }' \
 && rm -rf /var/lib/apt/lists/*
