// SPDX-License-Identifier: BSD-2-Clause
// Give malformed/unknown operation encodings a deterministic identity fallback.
@@
@@

- intmax_t offset;
+ intmax_t offset = lhs;
