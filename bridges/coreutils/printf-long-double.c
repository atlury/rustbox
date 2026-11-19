/* SPDX-License-Identifier: GPL-3.0-or-later
   Typed boundaries for GNU printf's native long-double representation.  */

#include <config.h>

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "cl-strtod.h"
#include "xprintf.h"

void
rustbox_printf_parse_long_double (char const *text, char **end, void *raw)
{
  long double value = cl_strtold (text, end);
  memcpy (raw, &value, sizeof value);
}

void
rustbox_printf_long_double_from_intmax (intmax_t integer, void *raw)
{
  long double value = integer;
  memcpy (raw, &value, sizeof value);
}

void
rustbox_printf_print_long_double (char const *format,
                                  bool have_field_width, int field_width,
                                  bool have_precision, int precision,
                                  void const *raw)
{
  long double value;
  memcpy (&value, raw, sizeof value);

  if (!have_field_width)
    {
      if (!have_precision)
        xprintf (format, value);
      else
        xprintf (format, precision, value);
    }
  else
    {
      if (!have_precision)
        xprintf (format, field_width, value);
      else
        xprintf (format, field_width, precision, value);
    }
}
