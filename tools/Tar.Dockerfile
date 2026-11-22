ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

# GNU tar's canonical test suite probes external compression personalities.
# These are oracle fixtures only; Rustbox's final applet must use its already
# integrated compression engines and retain no external runtime dependency.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bzip2 gzip lzip ncompress zstd \
 && rm -rf /var/lib/apt/lists/*
