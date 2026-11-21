ARG BASE_IMAGE=rustbox-normalize:2026-11-19
FROM ${BASE_IMAGE}

# XZ Utils is self-contained.  Keep its canonical command, liblzma, analyzer,
# sanitizer, C2Rust, and Valgrind work in the shared immutable toolchain.
