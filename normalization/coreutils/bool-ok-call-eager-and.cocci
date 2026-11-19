// SPDX-License-Identifier: GPL-3.0-or-later
@@
identifier function;
expression list arguments;
@@
-ok &= function(arguments);
+ok = function(arguments) && ok;
