// SPDX-License-Identifier: GPL-3.0-or-later
// Split the two initialized declarators so later typed rewrites are explicit.
@@
type T;
identifier first, second;
expression left, right;
@@
-T first = left, second = right;
+T first = left;
+T second = right;
