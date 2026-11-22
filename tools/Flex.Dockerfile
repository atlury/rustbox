ARG BASE_IMAGE=rustbox-gawk:2026-11-22
FROM ${BASE_IMAGE}

# Flex's signed release archive ships its generated parsers, scanners,
# documentation, and complete tests.  The inherited image already provides
# both C/C++ compilers, Bison, Autoconf, gettext, analyzers, sanitizers,
# Valgrind, Coccinelle, C2Rust, and Rust 1.99, so no package-specific host
# dependency is needed.
