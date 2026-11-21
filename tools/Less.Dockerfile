ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

# Less 710 builds against the terminal-info development archive already
# frozen in the shared tool image.  Keep a package-specific image name so
# its oracle and translation environment remains explicit and reproducible.
