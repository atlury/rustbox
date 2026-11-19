// SPDX-License-Identifier: GPL-3.0-or-later
@@
expression result, call;
@@
- result &= call;
+ result = call && result;
