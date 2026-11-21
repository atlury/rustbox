ARG BASE_IMAGE=rustbox-grep:2026-11-21
FROM ${BASE_IMAGE}

# GNU Gzip has no C build dependency.  Its canonical build installs zless only
# when less is present, so freeze that utility here to retain the complete
# 14-name installed surface requested by Rustbox.
RUN apt-get update \
    && apt-get install -y --no-install-recommends less \
    && rm -rf /var/lib/apt/lists/*
