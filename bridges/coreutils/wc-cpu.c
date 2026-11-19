/* SPDX-License-Identifier: GPL-3.0-or-later
   Typed boundary for GNU wc's canonical CPU feature probes.  */

#include <config.h>

#include <stdbool.h>

#include "cpu-supports.h"

bool
rustbox_wc_cpu_supports_avx2 (void)
{
  return cpu_supports ("avx2");
}

bool
rustbox_wc_cpu_supports_avx512 (void)
{
  return cpu_supports ("avx512f") && cpu_supports ("avx512bw");
}
