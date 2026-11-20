ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# File's canonical compression and sandbox feature set.  Keep these in a
# package-specific layer rather than perturbing the frozen shared tool image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libbz2-dev=1.0.8-5.1ubuntu0.1 \
      liblz-dev=1.14-1 \
      liblzma-dev=5.6.1+really5.4.5-1ubuntu0.4 \
      libseccomp-dev=2.5.5-1ubuntu3.1 \
 && rm -rf /var/lib/apt/lists/*
