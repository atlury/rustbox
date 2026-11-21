ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

# Canonical zstd is self-contained when optional foreign-format backends are
# disabled. Keep oracle, sanitizer, analyzer, C2Rust, and Valgrind work in the
# shared immutable normalization toolchain.
