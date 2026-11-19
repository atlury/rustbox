/* SPDX-License-Identifier: GPL-3.0-or-later
   Typed boundaries for GNU seq's native long-double representation.  */

#include <config.h>

#include <locale.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "system.h"
#include "cl-strtod.h"
#include "xstrtod.h"
#include "xvasprintf.h"

enum
{
  RUSTBOX_SEQ_NAN = 1,
  RUSTBOX_SEQ_FINITE = 2,
  RUSTBOX_SEQ_ZERO = 4,
  RUSTBOX_SEQ_NONNEGATIVE = 8,
  RUSTBOX_SEQ_FAST_STEP = 16
};

static long double
load_value (void const *raw)
{
  long double value;
  memcpy (&value, raw, sizeof value);
  return value;
}

static void
store_value (void *raw, long double value)
{
  memcpy (raw, &value, sizeof value);
}

bool
rustbox_seq_parse (char const *text, void *raw)
{
  long double value;
  bool valid = xstrtold (text, NULL, &value, cl_strtold);
  store_value (raw, value);
  return valid;
}

void
rustbox_seq_from_uintmax (uintmax_t integer, void *raw)
{
  store_value (raw, integer);
}

unsigned int
rustbox_seq_properties (void const *raw)
{
  long double value = load_value (raw);
  unsigned int properties = 0;
  if (value != value)
    properties |= RUSTBOX_SEQ_NAN;
  if (value * 0 == 0)
    properties |= RUSTBOX_SEQ_FINITE;
  if (value == 0)
    properties |= RUSTBOX_SEQ_ZERO;
  if (0 <= value)
    properties |= RUSTBOX_SEQ_NONNEGATIVE;
  if (0 < value && value <= 200)
    properties |= RUSTBOX_SEQ_FAST_STEP;
  return properties;
}

uintmax_t
rustbox_seq_to_uintmax (void const *raw)
{
  return load_value (raw);
}

char *
rustbox_seq_format_integer (void const *raw)
{
  return xasprintf ("%0.Lf", load_value (raw));
}

void
rustbox_seq_print_numbers (char const *fmt, size_t prefix_len,
                           size_t suffix_len, void const *first_raw,
                           void const *step_raw, void const *last_raw,
                           bool locale_ok, char const *separator,
                           char const *terminator)
{
  long double first = load_value (first_raw);
  long double step = load_value (step_raw);
  long double last = load_value (last_raw);
  bool out_of_range = (step < 0 ? first < last : last < first);

  if (!out_of_range)
    {
      long double x = first;
      for (long double i = 1; ; i++)
        {
          long double x0 = x;
          if (printf (fmt, x) < 0)
            write_error ();
          if (out_of_range)
            break;

          x = first + i * step;
          out_of_range = (step < 0 ? x < last : last < x);

          if (out_of_range)
            {
              bool print_extra_number = false;
              if (locale_ok)
                setlocale (LC_NUMERIC, "C");
              char *x_str;
              int x_strlen = asprintf (&x_str, fmt, x);
              if (locale_ok)
                setlocale (LC_NUMERIC, "");
              if (x_strlen < 0)
                xalloc_die ();
              x_str[x_strlen - suffix_len] = '\0';

              long double x_val;
              if (xstrtold (x_str + prefix_len, NULL, &x_val, cl_strtold)
                  && x_val == last)
                {
                  char *x0_str = NULL;
                  int x0_strlen = asprintf (&x0_str, fmt, x0);
                  if (x0_strlen < 0)
                    xalloc_die ();
                  x0_str[x0_strlen - suffix_len] = '\0';
                  print_extra_number = !streq (x0_str, x_str);
                  free (x0_str);
                }
              free (x_str);
              if (!print_extra_number)
                break;
            }

          if (fputs (separator, stdout) == EOF)
            write_error ();
        }

      if (fputs (terminator, stdout) == EOF)
        write_error ();
    }
}
