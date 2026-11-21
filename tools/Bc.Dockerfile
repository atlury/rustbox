ARG BASE_IMAGE=rustbox-grep:2026-11-21
FROM ${BASE_IMAGE}

# GNU bc 1.08.2 ships generated parser and scanner sources.  The inherited
# frozen analysis image already contains Bison, Flex and every audit tool; the
# canonical oracle deliberately disables optional Readline/libedit support.
