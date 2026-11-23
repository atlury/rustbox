ARG BASE_IMAGE=rustbox-flex:2026-11-22
FROM ${BASE_IMAGE}

# Bison's signed release archive ships generated parsers, scanners,
# documentation, skeletons, and its complete testsuite.  The inherited image
# already contains GNU M4, Flex, C/C++ compilers, analyzers, sanitizers,
# Valgrind, Coccinelle, C2Rust, and Rust 1.99.  Java and D are intentionally
# absent from Rustbox's Bison scope.
