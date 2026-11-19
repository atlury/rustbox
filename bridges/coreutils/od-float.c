/* SPDX-License-Identifier: GPL-3.0-or-later
   Typed boundaries for GNU od floating representations unsupported by C2Rust.  */

#include <config.h>

#include <stddef.h>
#include <string.h>

#include "ftoastr.h"

void
rustbox_od_halffloat_to_string (char *buf, size_t size, void const *raw)
{
  _Float16 value;
  memcpy (&value, raw, sizeof value);
  ftoastr (buf, size, 0, 0, value);
}

void
rustbox_od_bfloat_to_string (char *buf, size_t size, void const *raw)
{
  __bf16 value;
  memcpy (&value, raw, sizeof value);
  ftoastr (buf, size, 0, 0, value);
}

void
rustbox_od_long_double_to_string (char *buf, size_t size, void const *raw)
{
  long double value;
  memcpy (&value, raw, sizeof value);
  ldtoastr (buf, size, 0, 0, value);
}
