// SPDX-License-Identifier: GPL-3.0-or-later
// Preserve eager sync_arg evaluation while spelling the bool result explicitly.
@@
expression mode, argv, optind;
@@
- ok &= sync_arg (mode, argv[optind]);
+ ok = sync_arg (mode, argv[optind]) && ok;
