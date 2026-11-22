ARG BASE_IMAGE=rustbox-file:2026-11-20
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends dejagnu expect \
 && rm -rf /var/lib/apt/lists/*
