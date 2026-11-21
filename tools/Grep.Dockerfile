ARG BASE_IMAGE=rustbox-diffutils:2026-11-20
FROM ${BASE_IMAGE}

# GNU Grep 3.12 has no package-specific build or runtime dependency.
# Perl and the locale/tooling surface needed by its upstream suite are already
# frozen in the inherited Rustbox analysis image.
