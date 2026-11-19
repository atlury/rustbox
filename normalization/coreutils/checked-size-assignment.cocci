// SPDX-License-Identifier: GPL-3.0-or-later
@@
identifier e, size, tmp_size;
@@
- if (e == LONGINT_OK && ckd_add (size, tmp_size, 0))
-   e = LONGINT_OVERFLOW;
+ if (e == LONGINT_OK)
+   {
+     if (tmp_size > SIZE_MAX)
+       e = LONGINT_OVERFLOW;
+     else
+       *size = tmp_size;
+   }
