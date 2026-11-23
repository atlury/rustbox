ARG BASE_IMAGE=rustbox-bison:2026-11-23
FROM ${BASE_IMAGE}

# The Rustbox curl profile deliberately has no package-specific dependency.
# It keeps curl's internal HTTP/1 and non-TLS protocol implementations while
# disabling external TLS, compression, SSH, IDN, PSL, LDAP, HTTP/2, and HTTP/3
# libraries.  The inherited image already freezes both compilers, analyzers,
# sanitizers, Valgrind, Coccinelle, C2Rust, Perl, and the test harness tools.
