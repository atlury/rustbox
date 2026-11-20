ARG BASE_IMAGE=rustbox-file:2026-11-20
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# GNU patch's canonical suite exercises ed-script patches when ed is present.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ed=1.20.1-1 \
 && rm -rf /var/lib/apt/lists/*
