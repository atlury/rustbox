/* SPDX-License-Identifier: GPL-3.0-or-later
   Typed native-long-double comparisons for GNU sort.  */

#include <config.h>

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int
nan_compare (long double a, long double b)
{
  char buf[2][sizeof "-nan""()" + CHAR_BIT * sizeof a];
  snprintf (buf[0], sizeof buf[0], "%Lf", a);
  snprintf (buf[1], sizeof buf[1], "%Lf", b);
  return strcmp (buf[0], buf[1]);
}

int
rustbox_sort_general_numcompare (char const *sa, char const *sb)
{
  char *ea;
  char *eb;
  long double a = strtold (sa, &ea);
  long double b = strtold (sb, &eb);

  if (sa == ea)
    return sb == eb ? 0 : -1;
  if (sb == eb)
    return 1;

  return (a < b ? -1
          : a > b ? 1
          : a == b ? 0
          : b == b ? -1
          : a == a ? 1
          : nan_compare (a, b));
}

char *
rustbox_sort_strtold_end (char const *text)
{
  char *end;
  (void) strtold (text, &end);
  return end;
}
