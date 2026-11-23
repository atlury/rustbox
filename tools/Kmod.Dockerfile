ARG BASE_IMAGE=rustbox-inetutils:2026-11-23
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Kmod 34.3 no longer ships prebuilt module fixtures.  A fixed Ubuntu kernel
# header family is needed only to compile its synthetic upstream-test modules;
# the resulting utilities do not depend on that kernel version.
RUN apt-get update \
 && apt-get install -y --no-install-recommends linux-headers-generic zstd \
 && rm -rf /var/lib/apt/lists/*
