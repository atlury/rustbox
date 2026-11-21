ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

# LZ4's command and library are self-contained; retain the shared immutable
# normalization toolchain so every compiler/analyzer result is reproducible.
