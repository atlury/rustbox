/* SPDX-License-Identifier: GPL-3.0-or-later
   Canonical GNU numfmt numeric engine behind a typed C boundary.  */

#ifdef main
# undef main
#endif
#ifdef usage
# undef usage
#endif
#define main rustbox_numfmt_unused_main
#define usage rustbox_numfmt_unused_usage
#include "numfmt.c"
#undef main
#undef usage

bool
rustbox_numfmt_process_number (
  char *text, uintmax_t field, int configured_scale_from,
  int configured_scale_to, int configured_round_style,
  int configured_inval_style, char const *configured_suffix,
  char const *configured_unit_separator, uintmax_t configured_from_unit_size,
  uintmax_t configured_to_unit_size, int configured_grouping,
  intmax_t configured_padding_width, int configured_zero_padding_width,
  long int configured_user_precision, char const *configured_format_prefix,
  char const *configured_format_suffix, int configured_conv_exit_code,
  int configured_auto_padding, bool configured_debug,
  char const *configured_decimal_point, int configured_decimal_point_length,
  char const *configured_thousands_sep, int configured_thousands_sep_length,
  bool configured_dev_debug)
{
  scale_from = configured_scale_from;
  scale_to = configured_scale_to;
  round_style = configured_round_style;
  inval_style = configured_inval_style;
  suffix = configured_suffix;
  unit_separator = configured_unit_separator;
  from_unit_size = configured_from_unit_size;
  to_unit_size = configured_to_unit_size;
  grouping = configured_grouping;
  padding_width = configured_padding_width;
  zero_padding_width = configured_zero_padding_width;
  user_precision = configured_user_precision;
  format_str_prefix = (char *) configured_format_prefix;
  format_str_suffix = (char *) configured_format_suffix;
  conv_exit_code = configured_conv_exit_code;
  auto_padding = configured_auto_padding;
  debug = configured_debug;
  decimal_point = configured_decimal_point;
  decimal_point_length = configured_decimal_point_length;
  thousands_sep = configured_thousands_sep;
  thousands_sep_length = configured_thousands_sep_length;
  dev_debug = configured_dev_debug;

  long double val = 0;
  size_t precision = 0;
  bool valid_number = process_suffixed_number (text, &val, &precision, field);
  intmax_t padding;
  if (valid_number)
    valid_number = prepare_padded_number (val, precision, &padding);
  if (valid_number)
    print_padded_number (padding);
  else
    fputs (text, stdout);
  return valid_number;
}
