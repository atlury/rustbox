ARG BASE_IMAGE=rustbox-kmod:2026-11-24
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive

# Procps-ng's complete canonical suite is DejaGNU-driven.  Ncurses and the
# remaining compiler/audit tools are inherited; systemd, elogind, and SELinux
# development packages are deliberately not needed by Rustbox's profile.
RUN apt-get update \
 && apt-get install -y --no-install-recommends dejagnu expect \
 && rm -rf /var/lib/apt/lists/*
