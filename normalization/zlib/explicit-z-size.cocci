// SPDX-License-Identifier: GPL-3.0-or-later
// Make same-width unsigned-long to size_t conversions explicit for C2Rust.
@@
expression destLen;
@@
z_size_t got =
- *destLen
+ (z_size_t)*destLen
;

@@
expression sourceLen;
@@
z_size_t used =
- *sourceLen
+ (z_size_t)*sourceLen
;
