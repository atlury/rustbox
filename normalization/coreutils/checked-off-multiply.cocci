// SPDX-License-Identifier: GPL-3.0-or-later
@@
identifier ssize, blksize, ssize0;
@@
 intmax_t ssize0 = ssize;
+intmax_t product;
-if (ckd_mul (&ssize, ssize, blksize))
+if (ckd_mul (&product, ssize0, (intmax_t) blksize)
+    || product < TYPE_MINIMUM (off_t)
+    || TYPE_MAXIMUM (off_t) < product)
   {
   ...
   return false;
   }
+ssize = product;
