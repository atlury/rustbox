ARG BASE_IMAGE=rustbox-iproute2:2026-11-24
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Complete canonical E2fsprogs utility surface.  Systemd installation is
# disabled at configure time; these libraries exist only in the disposable
# oracle and must not become final Rustbox runtime dependencies.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bc gettext libarchive-dev libblkid-dev libfuse3-dev libmagic-dev uuid-dev \
 && rm -rf /var/lib/apt/lists/*
