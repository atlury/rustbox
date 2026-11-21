/* SPDX-License-Identifier: GPL-3.0-or-later
   Native equivalents of GNU Gzip 1.14's gunzip and zcat shell frontends. */
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_gzip_main(int, char **);

static int
run_gzip_mode(int argc, char **argv, char const *mode)
{
  char *gzip_argv[argc + 2];
  int index;
  gzip_argv[0] = (char *) "gzip";
  gzip_argv[1] = (char *) mode;
  for (index = 1; index <= argc; index++)
    gzip_argv[index + 1] = argv[index];
  program_invocation_name = gzip_argv[0];
  program_invocation_short_name = gzip_argv[0];
  return rustbox_gzip_main(argc + 1, gzip_argv);
}

static int
print_version(char const *name)
{
  return printf(
    "%s (gzip) 1.14\n"
    "Copyright (C) 2025 Free Software Foundation, Inc.\n"
    "This is free software.  You may redistribute copies of it under the terms of\n"
    "the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n"
    "There is NO WARRANTY, to the extent permitted by law.\n\n"
    "Written by Paul Eggert.\n", name) < 0;
}

int
rustbox_gunzip_main(int argc, char **argv)
{
  if (1 < argc && strcmp(argv[1], "--help") == 0)
    return printf(
      "Usage: %s [OPTION]... [FILE]...\n"
      "Uncompress FILEs (by default, in-place).\n\n"
      "Mandatory arguments to long options are mandatory for short options too.\n\n"
      "  -c, --stdout      write on standard output, keep original files unchanged\n"
      "  -f, --force       force overwrite of output file and compress links\n"
      "  -k, --keep        keep (don't delete) input files\n"
      "  -l, --list        list compressed file contents\n"
      "  -n, --no-name     do not save or restore the original name and timestamp\n"
      "  -N, --name        save or restore the original name and timestamp\n"
      "  -q, --quiet       suppress all warnings\n"
      "  -r, --recursive   operate recursively on directories\n"
      "  -S, --suffix=SUF  use suffix SUF on compressed files\n"
      "      --synchronous synchronous output (safer if system crashes, but slower)\n"
      "  -t, --test        test compressed file integrity\n"
      "  -v, --verbose     verbose mode\n"
      "      --help        display this help and exit\n"
      "      --version     display version information and exit\n\n"
      "With no FILE, or when FILE is -, read standard input.\n\n"
      "Report bugs to <bug-gzip@gnu.org>.\n", argv[0]) < 0;
  if (1 < argc && strcmp(argv[1], "--version") == 0)
    return print_version("gunzip");
  return run_gzip_mode(argc, argv, "-d");
}

int
rustbox_zcat_main(int argc, char **argv)
{
  if (1 < argc && strcmp(argv[1], "--help") == 0)
    return printf(
      "Usage: %s [OPTION]... [FILE]...\n"
      "Uncompress FILEs to standard output.\n\n"
      "  -f, --force       force; read compressed data even from a terminal\n"
      "  -l, --list        list compressed file contents\n"
      "  -q, --quiet       suppress all warnings\n"
      "  -r, --recursive   operate recursively on directories\n"
      "  -S, --suffix=SUF  use suffix SUF on compressed files\n"
      "      --synchronous synchronous output (safer if system crashes, but slower)\n"
      "  -t, --test        test compressed file integrity\n"
      "  -v, --verbose     verbose mode\n"
      "      --help        display this help and exit\n"
      "      --version     display version information and exit\n\n"
      "With no FILE, or when FILE is -, read standard input.\n\n"
      "Report bugs to <bug-gzip@gnu.org>.\n", argv[0]) < 0;
  if (1 < argc && strcmp(argv[1], "--version") == 0)
    return print_version("zcat");
  return run_gzip_mode(argc, argv, "-cd");
}
