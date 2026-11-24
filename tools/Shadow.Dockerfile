ARG BASE_IMAGE=rustbox-procps:2026-11-24
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Shadow's in-tree unit tests use CMocka.  Pytest and YAML support are kept for
# the later disposable-container system-test pass.  SELinux and systemd are
# deliberately disabled by configure rather than added as dependencies.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libcmocka-dev python3-pytest python3-yaml \
 && rm -rf /var/lib/apt/lists/*
