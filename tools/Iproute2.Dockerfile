ARG BASE_IMAGE=rustbox-shadow:2026-11-24
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Build every canonical IPRoute2 frontend except the explicitly excluded
# SELinux hook.  These libraries belong to the disposable oracle environment;
# the final Rustbox artifact must not gain runtime package dependencies.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bison flex libbpf-dev libcap-dev libdb-dev libelf-dev libmnl-dev libtirpc-dev \
      libxtables-dev \
 && rm -rf /var/lib/apt/lists/*
