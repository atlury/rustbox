/* SPDX-License-Identifier: GPL-3.0-or-later
   Native equivalents of GNU Gzip 1.14's shell frontends. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <utime.h>
#include <unistd.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_gzip_main(int, char **);
extern int rustbox_cmp_main(int, char **);
extern int rustbox_diff_main(int, char **);
extern int rustbox_grep_main(int, char **);
extern int rustbox_more_main(int, char **);
extern int rustbox_less_main(int, char **);

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

static int
has_compressed_suffix(char const *name)
{
  char const *p;
  size_t length = strlen(name);
  if (strcmp(name, "-") == 0)
    return 1;
  for (p = name; *p; p++)
    if ((*p == '-' || *p == '.') && p[1] == 'g' && p[2] == 'z')
      return 1;
  return (2 <= length
          && (name[length - 2] == '-' || name[length - 2] == '.')
          && (name[length - 1] == 'z' || name[length - 1] == 'Z'))
         || (4 <= length && name[length - 4] == '.' && name[length - 3] == 't'
             && (name[length - 2] == 'g' || name[length - 2] == 'a')
             && name[length - 1] == 'z');
}

static char *
uncompressed_name(char const *name)
{
  char *copy = strdup(name);
  char *suffix = NULL;
  char *p;
  if (!copy)
    return NULL;
  for (p = copy; *p; p++)
    if (*p == '-' || *p == '.')
      suffix = p;
  if (!suffix)
    {
      free(copy);
      return NULL;
    }
  for (p = suffix + 1; *p; p++)
    if (!strchr("zZtga", *p))
      {
        free(copy);
        return NULL;
      }
  *suffix = '\0';
  return copy;
}

static pid_t
start_gzip(char const *name, int output, int close_fd)
{
  pid_t child;
  fflush(NULL);
  child = fork();
  if (child != 0)
    return child;
  if (output != STDOUT_FILENO)
    {
      if (dup2(output, STDOUT_FILENO) < 0)
        _exit(2);
      close(output);
    }
  if (0 <= close_fd)
    close(close_fd);
  {
    char *gzip_argv[] = {
      (char *) "gzip", (char *) "-cdfq", (char *) "--", (char *) name, NULL
    };
    int status;
    program_invocation_name = gzip_argv[0];
    program_invocation_short_name = gzip_argv[0];
    status = rustbox_gzip_main(4, gzip_argv);
    fflush(NULL);
    _exit(status);
  }
}

static int
wait_gzip(pid_t child)
{
  int status;
  while (waitpid(child, &status, 0) < 0)
    if (errno != EINTR)
      return 2;
  return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : 2;
}

static int
print_zdiff_version(char const *name, char const *author)
{
  return printf(
    "%s (gzip) 1.14\n"
    "Copyright (C) 2025 Free Software Foundation, Inc.\n"
    "This is free software.  You may redistribute copies of it under the terms of\n"
    "the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n"
    "There is NO WARRANTY, to the extent permitted by law.\n\n"
    "Written by %s.\n", name, author) < 0 ? 2 : 0;
}

static int
print_zdiff_usage(char const *invocation, char const *program)
{
  return printf(
    "Usage: %s [OPTION]... FILE1 [FILE2]\n"
    "Compare FILE1 to FILE2, using their uncompressed contents if they are\n"
    "compressed.  If FILE2 is omitted, compare FILE1 to the uncompressed\n"
    "contents of FILE1.gz.  Do comparisons like '%s' does.\n\n"
    "OPTIONs are the same as for '%s'.\n\n"
    "Report bugs to <bug-gzip@gnu.org>.\n", invocation, program, program) < 0 ? 2 : 0;
}

static int
run_zdiff(int argc, char **argv, int use_cmp)
{
  char *compare_argv[argc + 4];
  char const *file1 = NULL;
  char const *file2 = NULL;
  char *derived = NULL;
  char const *program = use_cmp ? "cmp" : "diff";
  int compare_argc = 1;
  int files_only = 0;
  int need_operand = 0;
  int index;
  int first_compressed;
  int second_compressed;
  int first_pipe[2] = {-1, -1};
  int second_pipe[2] = {-1, -1};
  pid_t first_child = -1;
  pid_t second_child = -1;
  int compare_status;
  int gzip_status = 0;

  compare_argv[0] = (char *) program;
  for (index = 1; index < argc; index++)
    {
      char *argument = argv[index];
      if (!files_only && !need_operand
          && (strncmp(argument, "--h", 3) == 0
              || strncmp(argument, "--v", 3) == 0))
        return argument[2] == 'h'
               ? print_zdiff_usage(argv[0], program)
               : print_zdiff_version(use_cmp ? "zcmp" : "zdiff",
                                     "Jean-loup Gailly");
      if (!files_only && !need_operand && strcmp(argument, "--") == 0)
        {
          files_only = 1;
          compare_argv[compare_argc++] = argument;
          continue;
        }
      if (need_operand)
        {
          compare_argv[compare_argc++] = argument;
          need_operand = 0;
          continue;
        }
      if (!files_only && argument[0] == '-' && argument[1] != '\0')
        {
          compare_argv[compare_argc++] = argument;
          if (argument[2] == '\0' && strchr("CDFISUWXx", argument[1]))
            need_operand = 1;
          continue;
        }
      if (argument[0] == '\0')
        {
          fprintf(stderr, "%s: empty file name\n", argv[0]);
          return 2;
        }
      if (!file1)
        file1 = argument;
      else if (!file2)
        file2 = argument;
      else
        {
          fprintf(stderr, "%s: extra operand '%s'\n", argv[0], argument);
          return 2;
        }
    }
  if (need_operand)
    {
      fprintf(stderr, "%s: option requires an argument\n", argv[0]);
      return 2;
    }
  if (!file1)
    {
      fprintf(stderr, "%s: missing operand\n", argv[0]);
      return 2;
    }
  if (strcmp(file1, "-") != 0 && access(file1, R_OK) != 0)
    return 2;
  if (file2 && strcmp(file2, "-") != 0 && access(file2, R_OK) != 0)
    return 2;
  if (!file2)
    {
      if (!has_compressed_suffix(file1) || strcmp(file1, "-") == 0)
        {
          fprintf(stderr, "%s: %s: unknown compressed file extension\n",
                  argv[0], file1);
          return 2;
        }
      derived = uncompressed_name(file1);
      if (!derived)
        return 2;
      file2 = derived;
      if (access(file2, R_OK) != 0)
        {
          free(derived);
          return 2;
        }
    }

  first_compressed = has_compressed_suffix(file1);
  second_compressed = has_compressed_suffix(file2);
  if (first_compressed && second_compressed
      && strcmp(file1, "-") == 0 && strcmp(file2, "-") == 0)
    second_compressed = 0;

  if (first_compressed && pipe(first_pipe) < 0)
    goto system_error;
  if (second_compressed && pipe(second_pipe) < 0)
    goto system_error;
  if (first_compressed)
    {
      first_child = start_gzip(file1, first_pipe[1], first_pipe[0]);
      if (first_child < 0)
        goto system_error;
      close(first_pipe[1]);
      first_pipe[1] = -1;
    }
  if (second_compressed)
    {
      second_child = start_gzip(file2, second_pipe[1], second_pipe[0]);
      if (second_child < 0)
        goto system_error;
      close(second_pipe[1]);
      second_pipe[1] = -1;
    }

  if (first_compressed && second_compressed)
    {
      /* The second pipe commonly occupies fd 5.  Preserve it on stdin before
         installing the first stream at the canonical /dev/fd/5 name. */
      if (dup2(second_pipe[0], STDIN_FILENO) < 0 || dup2(first_pipe[0], 5) < 0)
        goto system_error;
      compare_argv[compare_argc++] = (char *) "/dev/fd/5";
      compare_argv[compare_argc++] = (char *) "-";
    }
  else if (first_compressed)
    {
      if (dup2(first_pipe[0], STDIN_FILENO) < 0)
        goto system_error;
      compare_argv[compare_argc++] = (char *) "-";
      compare_argv[compare_argc++] = (char *) file2;
    }
  else if (second_compressed)
    {
      if (dup2(second_pipe[0], STDIN_FILENO) < 0)
        goto system_error;
      compare_argv[compare_argc++] = (char *) file1;
      compare_argv[compare_argc++] = (char *) "-";
    }
  else
    {
      compare_argv[compare_argc++] = (char *) file1;
      compare_argv[compare_argc++] = (char *) file2;
    }
  compare_argv[compare_argc] = NULL;
  if (0 <= first_pipe[0] && first_pipe[0] != STDIN_FILENO && first_pipe[0] != 5)
    close(first_pipe[0]);
  if (0 <= second_pipe[0] && second_pipe[0] != STDIN_FILENO && second_pipe[0] != 5)
    close(second_pipe[0]);
  program_invocation_name = compare_argv[0];
  program_invocation_short_name = compare_argv[0];
  compare_status = use_cmp
                     ? rustbox_cmp_main(compare_argc, compare_argv)
                     : rustbox_diff_main(compare_argc, compare_argv);
  if (0 < first_child)
    gzip_status |= wait_gzip(first_child);
  if (0 < second_child)
    gzip_status |= wait_gzip(second_child);
  free(derived);
  return gzip_status ? 2 : compare_status;

system_error:
  if (0 <= first_pipe[0]) close(first_pipe[0]);
  if (0 <= first_pipe[1]) close(first_pipe[1]);
  if (0 <= second_pipe[0]) close(second_pipe[0]);
  if (0 <= second_pipe[1]) close(second_pipe[1]);
  if (0 < first_child) wait_gzip(first_child);
  if (0 < second_child) wait_gzip(second_child);
  free(derived);
  return 2;
}

int
rustbox_zcmp_main(int argc, char **argv)
{
  char const *slash;
  int index;
  size_t prefix;
  if (1 < argc && strcmp(argv[1], "--help") == 0)
    return printf(
      "Usage: %s [OPTION]... FILE1 [FILE2]\n"
      "Compare FILE1 to FILE2 byte by byte, using their uncompressed contents\n"
      "if they are compressed.  If FILE2 is omitted, compare FILE1 to the\n"
      "uncompressed contents of FILE1.gz.  Do comparisons like 'cmp' does.\n\n"
      "Options are the same as for 'cmp'.\n\n"
      "If a FILE is '-' or missing, read standard input.\n\n"
      "Report bugs to <bug-gzip@gnu.org>.\n", argv[0]) < 0 ? 2 : 0;
  if (1 < argc && strcmp(argv[1], "--version") == 0)
    return print_zdiff_version("zcmp", "Paul Eggert");
  slash = strrchr(argv[0], '/');
  prefix = slash ? (size_t) (slash - argv[0] + 1) : 0;
  {
    char backend_name[prefix + sizeof "zdiff"];
    char *backend_argv[argc + 1];
    if (prefix)
      memcpy(backend_name, argv[0], prefix);
    memcpy(backend_name + prefix, "zdiff", sizeof "zdiff");
    backend_argv[0] = backend_name;
    for (index = 1; index <= argc; index++)
      backend_argv[index] = argv[index];
    return run_zdiff(argc, backend_argv, 1);
  }
}

int
rustbox_zdiff_main(int argc, char **argv)
{
  return run_zdiff(argc, argv, 0);
}

static int
has_zforce_suffix(char const *name)
{
  size_t length = strlen(name);
  return (2 <= length
          && (name[length - 2] == '-' || name[length - 2] == '.')
          && name[length - 1] == 'z')
         || (3 <= length
             && (name[length - 3] == '-' || name[length - 3] == '.')
             && name[length - 2] == 'g' && name[length - 1] == 'z')
         || (4 <= length && name[length - 4] == '.' && name[length - 3] == 't'
             && (name[length - 2] == 'a' || name[length - 2] == 'g')
             && name[length - 1] == 'z');
}

static int
gzip_lists_deflate(char const *name)
{
  int output[2];
  pid_t child;
  char listing[4096];
  size_t used = 0;
  char discard[256];
  ssize_t count;
  int input;
  int nullfd;
  if (pipe(output) < 0)
    return 0;
  fflush(NULL);
  child = fork();
  if (child < 0)
    {
      close(output[0]);
      close(output[1]);
      return 0;
    }
  if (child == 0)
    {
      char *gzip_argv[] = {(char *) "gzip", (char *) "-lv", NULL};
      int gzip_status;
      close(output[0]);
      input = open(name, O_RDONLY);
      nullfd = open("/dev/null", O_WRONLY);
      if (input < 0 || nullfd < 0
          || dup2(input, STDIN_FILENO) < 0
          || dup2(output[1], STDOUT_FILENO) < 0
          || dup2(nullfd, STDERR_FILENO) < 0)
        _exit(1);
      close(input);
      close(nullfd);
      close(output[1]);
      program_invocation_name = gzip_argv[0];
      program_invocation_short_name = gzip_argv[0];
      gzip_status = rustbox_gzip_main(2, gzip_argv);
      fflush(NULL);
      _exit(gzip_status);
    }
  close(output[1]);
  while (used + 1 < sizeof listing
         && (count = read(output[0], listing + used,
                          sizeof listing - used - 1)) > 0)
    used += (size_t) count;
  while (read(output[0], discard, sizeof discard) > 0)
    continue;
  close(output[0]);
  wait_gzip(child);
  listing[used] = '\0';
  return (used >= 4 && memcmp(listing, "defl", 4) == 0)
         || strstr(listing, "\ndefl") != NULL;
}

int
rustbox_zforce_main(int argc, char **argv)
{
  int result = 0;
  int index;
  if (argc == 1)
    {
      fprintf(stderr,
              "%s: invalid number of operands; try `%s --help' for help\n",
              argv[0], argv[0]);
      return 1;
    }
  for (index = 1; index < argc; index++)
    {
      char const *name = argv[index];
      struct stat status;
      size_t length;
      if (strncmp(name, "--h", 3) == 0)
        return printf(
          "Usage: %s [FILE]...\n"
          "Force a .gz extension on all compressed FILEs so that gzip will\n"
          "not compress them twice.\n\n"
          "Report bugs to <bug-gzip@gnu.org>.\n", argv[0]) < 0;
      if (strncmp(name, "--v", 3) == 0)
        return print_zdiff_version("zforce", "Jean-loup Gailly") == 2;
      if (has_zforce_suffix(name))
        continue;
      if (stat(name, &status) != 0 || !S_ISREG(status.st_mode))
        {
          printf("zforce: %s not a file\n", name);
          result = 1;
          continue;
        }
      if (gzip_lists_deflate(name))
        {
          length = strlen(name);
          {
            char replacement[length + sizeof ".gz"];
            memcpy(replacement, name, length);
            memcpy(replacement + length, ".gz", sizeof ".gz");
            if (rename(name, replacement) == 0)
              printf("%s -- replaced with %s\n", name, replacement);
            else
              result = 1;
          }
        }
    }
  return result;
}

static int
zgrep_usage(char const *invocation)
{
  return printf(
    "Usage: %s [OPTION]... [-e] PATTERN [FILE]...\n"
    "Look for instances of PATTERN in the input FILEs, using their\n"
    "uncompressed contents if they are compressed.\n\n"
    "OPTIONs are the same as for 'grep', except that the following 'grep'\n"
    "options are not supported: --dereference-recursive (-R), --directories (-d),\n"
    "--exclude, --exclude-from, --exclude-dir, --include, --null (-Z),\n"
    "--null-data (-z), and --recursive (-r).\n\n"
    "Report bugs to <bug-gzip@gnu.org>.\n", invocation) < 0 ? 2 : 0;
}

static int
zgrep_version(void)
{
  return printf(
    "zgrep (gzip) 1.14\n"
    "Copyright (C) 2025 Free Software Foundation, Inc.\n"
    "This is free software.  You may redistribute copies of it under the terms of\n"
    "the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n"
    "There is NO WARRANTY, to the extent permitted by law.\n\n"
    "Written by Jean-loup Gailly.\n") < 0 ? 2 : 0;
}

static int
wait_program(pid_t child)
{
  int status;
  while (waitpid(child, &status, 0) < 0)
    if (errno != EINTR)
      return 2;
  if (WIFEXITED(status))
    return WEXITSTATUS(status);
  if (WIFSIGNALED(status))
    return 128 + WTERMSIG(status);
  return 2;
}

static int
zgrep_file(char const *name, int grep_argc, char **grep_argv,
           int with_filename, int files_with_matches,
           int files_without_matches)
{
  int stream[2];
  int nullfd = -1;
  pid_t gzip_child;
  pid_t grep_child;
  int gzip_status;
  int grep_status;
  if (pipe(stream) < 0)
    return 2;
  gzip_child = start_gzip(name, stream[1], stream[0]);
  if (gzip_child < 0)
    {
      close(stream[0]);
      close(stream[1]);
      return 2;
    }
  close(stream[1]);
  fflush(NULL);
  grep_child = fork();
  if (grep_child < 0)
    {
      close(stream[0]);
      wait_program(gzip_child);
      return 2;
    }
  if (grep_child == 0)
    {
      char *child_argv[grep_argc + 4];
      char label[strlen(name) + sizeof "--label="];
      int child_argc = 0;
      int index;
      if (dup2(stream[0], STDIN_FILENO) < 0)
        _exit(2);
      close(stream[0]);
      if (files_with_matches || files_without_matches)
        {
          nullfd = open("/dev/null", O_WRONLY);
          if (nullfd < 0 || dup2(nullfd, STDOUT_FILENO) < 0)
            _exit(2);
          close(nullfd);
        }
      child_argv[child_argc++] = (char *) "grep";
      if (with_filename)
        {
          child_argv[child_argc++] = (char *) "-H";
          if (strcmp(name, "-") != 0)
            {
              memcpy(label, "--label=", sizeof "--label=" - 1);
              strcpy(label + sizeof "--label=" - 1, name);
              child_argv[child_argc++] = label;
            }
        }
      for (index = 1; index < grep_argc; index++)
        child_argv[child_argc++] = grep_argv[index];
      child_argv[child_argc] = NULL;
      program_invocation_name = child_argv[0];
      program_invocation_short_name = child_argv[0];
      grep_status = rustbox_grep_main(child_argc, child_argv);
      fflush(NULL);
      exit(grep_status);
    }
  close(stream[0]);
  grep_status = wait_program(grep_child);
  gzip_status = wait_program(gzip_child);
  if (gzip_status == 2 || gzip_status == 141)
    gzip_status = 0;
  else if (gzip_status == 1)
    gzip_status = 2;
  else if (gzip_status != 0)
    gzip_status = 2;
  if (files_with_matches && grep_status == 0)
    {
      if (printf("%s\n", name) < 0)
        grep_status = 2;
    }
  else if (files_without_matches && grep_status == 1)
    {
      if (printf("%s\n", name) < 0)
        grep_status = 2;
      else
        grep_status = 0;
    }
  return grep_status < gzip_status ? gzip_status : grep_status;
}

static int
zgrep_abbreviation(char const *option, char const *full, size_t minimum)
{
  size_t length = strlen(option);
  return minimum <= length && length <= strlen(full)
         && memcmp(option, full, length) == 0;
}

static int
zgrep_unsupported(char const *option)
{
  return strcmp(option, "-d") == 0 || strcmp(option, "-r") == 0
         || strcmp(option, "-R") == 0 || strcmp(option, "-z") == 0
         || strcmp(option, "-Z") == 0
         || strncmp(option, "--di", 4) == 0
         || strncmp(option, "--exclude", 9) == 0
         || strncmp(option, "--include", 9) == 0
         || strncmp(option, "--rec", 5) == 0
         || strncmp(option, "--nu", 4) == 0;
}

static int
zgrep_option_takes_argument(char const *option)
{
  return strcmp(option, "-A") == 0 || strcmp(option, "-B") == 0
         || strcmp(option, "-C") == 0 || strcmp(option, "-D") == 0
         || strcmp(option, "-X") == 0 || strcmp(option, "-e") == 0
         || strcmp(option, "-f") == 0 || strcmp(option, "-m") == 0
         || strcmp(option, "--binary-files") == 0
         || strcmp(option, "--label") == 0
         || strcmp(option, "--max-count") == 0
         || strcmp(option, "--regexp") == 0
         || strcmp(option, "--file") == 0;
}

static int
run_zgrep(int argc, char **argv, char const *personality)
{
  char *grep_argv[argc + 4];
  char *files[argc + 1];
  char invocation[strlen(argv[0]) + 1];
  char *pattern = NULL;
  int grep_argc = 1;
  int file_count = 0;
  int options = 1;
  int have_pattern = 0;
  int with_filename = 0;
  int no_filename = 0;
  int files_with_matches = 0;
  int files_without_matches = 0;
  int result = 1;
  int index;
  if (personality)
    {
      char const *slash = strrchr(argv[0], '/');
      size_t prefix = slash ? (size_t) (slash - argv[0] + 1) : 0;
      if (prefix)
        memcpy(invocation, argv[0], prefix);
      memcpy(invocation + prefix, "zgrep", sizeof "zgrep");
    }
  else
    strcpy(invocation, argv[0]);
  grep_argv[0] = (char *) "grep";
  if (personality)
    grep_argv[grep_argc++] = (char *) personality;
  for (index = 1; index < argc; index++)
    {
      char *argument = argv[index];
      if (options && strcmp(argument, "--") == 0)
        {
          options = 0;
          continue;
        }
      if (options && argument[0] == '-' && argument[1] != '\0')
        {
          if (zgrep_abbreviation(argument, "--help", 3))
            return zgrep_usage(invocation);
          if (strcmp(argument, "-V") == 0
              || zgrep_abbreviation(argument, "--version", 3))
            return zgrep_version();
          if (zgrep_unsupported(argument))
            {
              fprintf(stderr, "%s: %s: option not supported\n", invocation,
                      argument);
              return 2;
            }
          if (strcmp(argument, "-H") == 0
              || zgrep_abbreviation(argument, "--with-filename", 4))
            with_filename = 1;
          if (strcmp(argument, "-h") == 0
              || zgrep_abbreviation(argument, "--no-filename", 6))
            no_filename = 1;
          if (strcmp(argument, "-l") == 0
              || zgrep_abbreviation(argument, "--files-with-matches", 14))
            files_with_matches = 1;
          if (strcmp(argument, "-L") == 0
              || zgrep_abbreviation(argument, "--files-without-match", 15))
            files_without_matches = 1;
          if (strncmp(argument, "-e", 2) == 0
              || strncmp(argument, "-f", 2) == 0
              || strncmp(argument, "--regexp", 8) == 0
              || strncmp(argument, "--file", 6) == 0)
            have_pattern = 1;
          grep_argv[grep_argc++] = argument;
          if (zgrep_option_takes_argument(argument))
            {
              if (++index == argc)
                {
                  fprintf(stderr, "%s: %s option requires an argument\n",
                          invocation, argument);
                  return 2;
                }
              grep_argv[grep_argc++] = argv[index];
            }
          continue;
        }
      if (!have_pattern)
        {
          pattern = argument;
          have_pattern = 1;
        }
      else
        files[file_count++] = argument;
    }
  if (!have_pattern)
    {
      fprintf(stderr, "%s: missing pattern; try `%s --help' for help\n",
              invocation, invocation);
      return 2;
    }
  if (pattern)
    {
      grep_argv[grep_argc++] = (char *) "--";
      grep_argv[grep_argc++] = pattern;
    }
  grep_argv[grep_argc] = NULL;
  if (file_count == 0)
    files[file_count++] = (char *) "-";
  else if (1 < file_count && !no_filename)
    with_filename = 1;
  for (index = 0; index < file_count; index++)
    {
      int status = zgrep_file(files[index], grep_argc, grep_argv, with_filename,
                              files_with_matches, files_without_matches);
      if (status <= 1 && result <= 1)
        {
          if (status < result)
            result = status;
        }
      else if (result < status)
        result = status;
      if (126 <= result)
        break;
    }
  return result;
}

int
rustbox_zgrep_main(int argc, char **argv)
{
  return run_zgrep(argc, argv, NULL);
}

int
rustbox_zegrep_main(int argc, char **argv)
{
  return run_zgrep(argc, argv, "-E");
}

int
rustbox_zfgrep_main(int argc, char **argv)
{
  return run_zgrep(argc, argv, "-F");
}

static int
zmore_help(char const *invocation)
{
  return printf(
    "Usage: %s [OPTION]... [FILE]...\n"
    "Like 'more', but operate on the uncompressed contents of any compressed FILEs.\n\n"
    "Report bugs to <bug-gzip@gnu.org>.\n", invocation) < 0;
}

static int
zless_help(char const *invocation)
{
  return printf(
    "Usage: %s [OPTION]... [FILE]...\n"
    "Like 'less', but operate on the uncompressed contents of any compressed FILEs.\n\n"
    "Options are the same as for 'less'.\n\n"
    "Report bugs to <bug-gzip@gnu.org>.\n", invocation) < 0;
}

static int
zless_version(void)
{
  return printf(
    "zless (gzip) 1.14\n"
    "Copyright (C) 2025 Free Software Foundation, Inc.\n"
    "This is free software.  You may redistribute copies of it under the terms of\n"
    "the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n"
    "There is NO WARRANTY, to the extent permitted by law.\n\n"
    "Written by Paul Eggert.\n") < 0;
}

static int
zless_option_takes_argument(char const *option)
{
  static char const *const long_options[] = {
    "buffers", "color", "max-back-scroll", "jump-target",
    "lesskey-file", "lesskey-src", "lesskey-content", "log-file",
    "LOG-FILE", "pattern", "prompt", "tag", "tag-file", "tabs",
    "max-forw-scroll", "window", "quotes", "shift", "rscroll",
    "emouse", "wheel-lines", "line-num-width", "status-col-width",
    "header", "search-options", "modelines", "intr", "cmd",
    "match-shift", "autosave", "end-prompt", "tty"
  };
  size_t index;
  size_t length;
  int matches = 0;
  if (option[0] != '-' || option[1] == '\0')
    return 0;
  if (option[1] != '-')
    {
      if (strcmp(option, "-kc") == 0 || strcmp(option, "-ks") == 0)
        return 1;
      return option[2] == '\0'
             && strchr("bDhjkoOpPtTxyz\"#", option[1]) != NULL;
    }
  if (option[2] == '\0' || strchr(option + 2, '=') != NULL)
    return 0;
  length = strlen(option + 2);
  for (index = 0; index < sizeof long_options / sizeof long_options[0]; index++)
    if (strncmp(long_options[index], option + 2, length) == 0)
      matches++;
  return matches == 1;
}

int
rustbox_zless_main(int argc, char **argv)
{
  int first = 1;
  int stream[2];
  pid_t producer;
  pid_t pager;
  int index;
  int pager_status;
  char *less_argv[argc + 1];
  int less_argc = 1;
  if (1 < argc && strcmp(argv[1], "--help") == 0)
    return zless_help(argv[0]);
  if (1 < argc && strcmp(argv[1], "--version") == 0)
    return zless_version();
  less_argv[0] = (char *) "less";
  while (first < argc)
    {
      if (strcmp(argv[first], "--") == 0)
        {
          first++;
          break;
        }
      if (argv[first][0] != '-' || argv[first][1] == '\0')
        {
          if (argv[first][0] == '+')
            {
              less_argv[less_argc++] = argv[first++];
              continue;
            }
          break;
        }
      less_argv[less_argc++] = argv[first++];
      if (zless_option_takes_argument(less_argv[less_argc - 1]) && first < argc)
        less_argv[less_argc++] = argv[first++];
    }
  less_argv[less_argc] = NULL;
  if (pipe(stream) < 0)
    return 1;
  fflush(NULL);
  producer = fork();
  if (producer < 0)
    {
      close(stream[0]);
      close(stream[1]);
      return 1;
    }
  if (producer == 0)
    {
      int file_count = argc - first;
      close(stream[0]);
      if (dup2(stream[1], STDOUT_FILENO) < 0)
        _exit(1);
      close(stream[1]);
      if (file_count == 0)
        {
          pid_t child = start_gzip("-", STDOUT_FILENO, -1);
          _exit(child < 0 ? 1 : wait_program(child));
        }
      for (index = first; index < argc; index++)
        {
          pid_t child = start_gzip(argv[index], STDOUT_FILENO, -1);
          if (child < 0 || wait_program(child) != 0)
            _exit(1);
        }
      _exit(0);
    }
  close(stream[1]);
  fflush(NULL);
  pager = fork();
  if (pager < 0)
    {
      close(stream[0]);
      wait_program(producer);
      return 1;
    }
  if (pager == 0)
    {
      int status;
      if (dup2(stream[0], STDIN_FILENO) < 0)
        _exit(1);
      close(stream[0]);
      program_invocation_name = less_argv[0];
      program_invocation_short_name = less_argv[0];
      status = rustbox_less_main(less_argc, less_argv);
      fflush(NULL);
      exit(status);
    }
  close(stream[0]);
  pager_status = wait_program(pager);
  if (wait_program(producer) != 0 && pager_status == 0)
    return 1;
  return pager_status;
}

static int
zmore_version(void)
{
  return printf(
    "zmore (gzip) 1.14\n"
    "Copyright (C) 2025 Free Software Foundation, Inc.\n"
    "This is free software.  You may redistribute copies of it under the terms of\n"
    "the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n"
    "There is NO WARRANTY, to the extent permitted by law.\n\n"
    "Written by Jean-loup Gailly.\n") < 0;
}

int
rustbox_zmore_main(int argc, char **argv)
{
  int first = 1;
  int stream[2];
  pid_t producer;
  pid_t pager;
  int index;
  int pager_status;
  if (1 < argc && strncmp(argv[1], "--h", 3) == 0)
    return zmore_help(argv[0]);
  if (1 < argc && strncmp(argv[1], "--v", 3) == 0)
    return zmore_version();
  if (1 < argc && strcmp(argv[1], "--") == 0)
    first++;
  else if (1 < argc && argv[1][0] == '-' && argv[1][1] != '\0')
    {
      fprintf(stderr, "%s: %s: unknown option; try '%s --help' for help\n",
              argv[0], argv[1], argv[0]);
      return 1;
    }
  if (first == argc && isatty(STDIN_FILENO))
    {
      fprintf(stderr, "%s: missing operands; try '%s --help' for help\n",
              argv[0], argv[0]);
      return 1;
    }
  if (pipe(stream) < 0)
    return 1;
  fflush(NULL);
  producer = fork();
  if (producer < 0)
    {
      close(stream[0]);
      close(stream[1]);
      return 1;
    }
  if (producer == 0)
    {
      int file_count = argc - first;
      close(stream[0]);
      if (dup2(stream[1], STDOUT_FILENO) < 0
          || dup2(stream[1], STDERR_FILENO) < 0)
        _exit(1);
      close(stream[1]);
      if (file_count == 0)
        {
          pid_t child = start_gzip("-", STDOUT_FILENO, -1);
          _exit(child < 0 ? 1 : wait_program(child));
        }
      for (index = first; index < argc; index++)
        {
          pid_t child;
          if (1 < file_count
              && dprintf(STDOUT_FILENO,
                         "::::::::::::::\n%s\n::::::::::::::\n", argv[index]) < 0)
            _exit(1);
          child = start_gzip(argv[index], STDOUT_FILENO, -1);
          if (child < 0 || wait_program(child) != 0)
            continue;
        }
      _exit(0);
    }
  close(stream[1]);
  fflush(NULL);
  pager = fork();
  if (pager < 0)
    {
      close(stream[0]);
      wait_program(producer);
      return 1;
    }
  if (pager == 0)
    {
      char *more_argv[] = {(char *) "more", NULL};
      int status;
      if (dup2(stream[0], STDIN_FILENO) < 0)
        _exit(1);
      close(stream[0]);
      program_invocation_name = more_argv[0];
      program_invocation_short_name = more_argv[0];
      status = rustbox_more_main(1, more_argv);
      fflush(NULL);
      exit(status);
    }
  close(stream[0]);
  pager_status = wait_program(pager);
  wait_program(producer);
  return pager_status;
}

static int
run_gzip_process(int argc, char **argv, int input, int output)
{
  pid_t child;
  fflush(NULL);
  child = fork();
  if (child < 0)
    return 1;
  if (child == 0)
    {
      int status;
      if ((0 <= input && input != STDIN_FILENO
           && dup2(input, STDIN_FILENO) < 0)
          || (0 <= output && output != STDOUT_FILENO
              && dup2(output, STDOUT_FILENO) < 0))
        _exit(1);
      if (2 < input)
        close(input);
      if (2 < output && output != input)
        close(output);
      program_invocation_name = argv[0];
      program_invocation_short_name = argv[0];
      status = rustbox_gzip_main(argc, argv);
      fflush(NULL);
      _exit(status);
    }
  return wait_program(child);
}

static int
copy_regular_file(char const *source, char const *destination)
{
  struct stat status;
  struct utimbuf times;
  char buffer[32768];
  int input = open(source, O_RDONLY);
  int output;
  ssize_t count;
  if (input < 0 || fstat(input, &status) != 0)
    {
      if (0 <= input)
        close(input);
      return 1;
    }
  output = open(destination, O_WRONLY | O_CREAT | O_TRUNC,
                status.st_mode & 07777);
  if (output < 0)
    {
      close(input);
      return 1;
    }
  while ((count = read(input, buffer, sizeof buffer)) > 0)
    {
      char *position = buffer;
      ssize_t remaining = count;
      while (0 < remaining)
        {
          ssize_t written = write(output, position, (size_t) remaining);
          if (written <= 0)
            goto failure;
          position += written;
          remaining -= written;
        }
    }
  if (count < 0 || fchmod(output, status.st_mode & 07777) != 0
      || close(input) != 0 || close(output) != 0)
    return 1;
  times.actime = status.st_atime;
  times.modtime = status.st_mtime;
  return utime(destination, &times) != 0;

failure:
  close(input);
  close(output);
  return 1;
}

static int
znew_pipe(char const *old_name, char const *new_name, char const *option)
{
  int stream[2];
  int input;
  int output;
  pid_t decompressor;
  pid_t compressor;
  int first_status;
  int second_status;
  char *decompress_argv[] = {(char *) "gzip", (char *) "-d", NULL};
  char *compress_argv[] = {(char *) "gzip", (char *) option, NULL};
  int compress_argc = option[0] ? 2 : 1;
  if (pipe(stream) < 0)
    return 1;
  input = open(old_name, O_RDONLY);
  output = open(new_name, O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (input < 0 || output < 0)
    {
      if (0 <= input) close(input);
      if (0 <= output) close(output);
      close(stream[0]);
      close(stream[1]);
      return 1;
    }
  fflush(NULL);
  decompressor = fork();
  if (decompressor == 0)
    {
      int status;
      close(stream[0]);
      if (dup2(input, STDIN_FILENO) < 0 || dup2(stream[1], STDOUT_FILENO) < 0)
        _exit(1);
      close(input);
      close(output);
      close(stream[1]);
      program_invocation_name = decompress_argv[0];
      program_invocation_short_name = decompress_argv[0];
      status = rustbox_gzip_main(2, decompress_argv);
      fflush(NULL);
      _exit(status);
    }
  if (decompressor < 0)
    goto failure;
  compressor = fork();
  if (compressor == 0)
    {
      int status;
      close(stream[1]);
      if (dup2(stream[0], STDIN_FILENO) < 0 || dup2(output, STDOUT_FILENO) < 0)
        _exit(1);
      close(input);
      close(output);
      close(stream[0]);
      program_invocation_name = compress_argv[0];
      program_invocation_short_name = compress_argv[0];
      status = rustbox_gzip_main(compress_argc, compress_argv);
      fflush(NULL);
      _exit(status);
    }
  if (compressor < 0)
    {
      close(input);
      close(output);
      close(stream[0]);
      close(stream[1]);
      wait_program(decompressor);
      return 1;
    }
  close(input);
  close(output);
  close(stream[0]);
  close(stream[1]);
  first_status = wait_program(decompressor);
  second_status = wait_program(compressor);
  return first_status != 0 || second_status != 0;

failure:
  close(input);
  close(output);
  close(stream[0]);
  close(stream[1]);
  return 1;
}

static int
znew_help(char const *invocation)
{
  return printf(
    "Usage: %s [OPTION]... [FILE]...\n"
    "Recompress files from .Z (compress) format to .gz (gzip) format.\n\n"
    "Options:\n\n"
    "  -f     Force recompression even if a .gz file already exists.\n"
    "  -t     Test the new files before deleting originals.\n"
    "  -v     Verbose; display name and statistics for each file compressed.\n"
    "  -9     Use the slowest compression method (optimal compression).\n"
    "  -P     Use pipes for the conversion to reduce disk space usage.\n"
    "  -K     Keep a .Z file when it is smaller than the .gz file; implies -t.\n"
    "      --help     display this help and exit\n"
    "      --version  output version information and exit\n\n"
    "Report bugs to <bug-gzip@gnu.org>.\n", invocation) < 0;
}

static int
znew_version(void)
{
  return printf(
    "znew (gzip) 1.14\n"
    "Copyright (C) 2025 Free Software Foundation, Inc.\n"
    "This is free software.  You may redistribute copies of it under the terms of\n"
    "the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n"
    "There is NO WARRANTY, to the extent permitted by law.\n\n"
    "Written by Jean-loup Gailly.\n") < 0;
}

int
rustbox_znew_main(int argc, char **argv)
{
  size_t option_capacity = 1;
  int first = 1;
  int check = 0;
  int use_pipe = 0;
  int keep = 0;
  int result = 0;
  int index;
  for (index = 1; index < argc && argv[index][0] == '-'; index++)
    option_capacity += strlen(argv[index]);
  {
    char options[option_capacity + 2];
    size_t option_length = 0;
    options[option_length++] = '-';
    while (first < argc && argv[first][0] == '-')
      {
        char const *p;
        if (strcmp(argv[first], "--help") == 0)
          return znew_help(argv[0]);
        if (strcmp(argv[first], "--version") == 0)
          return znew_version();
        for (p = argv[first]; *p; p++)
          if (*p != '-')
            {
              if (*p == 't') check = 1;
              else if (*p == 'K') { keep = 1; check = 1; }
              else if (*p == 'P') use_pipe = 1;
              else options[option_length++] = *p;
            }
        first++;
      }
    options[option_length] = '\0';
    if (option_length == 1)
      options[0] = '\0';
    if (first == argc)
      {
        fprintf(stderr,
                "%s: invalid number of operands; try `%s --help' for help\n",
                argv[0], argv[0]);
        return 1;
      }
    for (index = first; index < argc; index++)
      {
        char const *argument = argv[index];
        size_t length = strlen(argument);
        size_t base_length = 2 <= length && strcmp(argument + length - 2, ".Z") == 0
                               ? length - 2 : length;
        char base[base_length + 1];
        char old_name[base_length + sizeof ".Z"];
        char new_name[base_length + sizeof ".gz"];
        char backup[base_length + 32];
        struct stat old_status;
        struct stat new_status;
        int conversion_status;
        memcpy(base, argument, base_length);
        base[base_length] = '\0';
        snprintf(old_name, sizeof old_name, "%s.Z", base);
        snprintf(new_name, sizeof new_name, "%s.gz", base);
        snprintf(backup, sizeof backup, "%s%ld", base, (long) getpid());
        if (stat(old_name, &old_status) != 0 || !S_ISREG(old_status.st_mode))
          {
            printf("%s not found\n", old_name);
            result = 1;
            continue;
          }
        if (!use_pipe && check && copy_regular_file(old_name, backup) != 0)
          {
            printf("cannot backup %s\n", old_name);
            result = 1;
            continue;
          }
        if (use_pipe)
          conversion_status = znew_pipe(old_name, new_name, options);
        else
          {
            char *decompress_argv[] = {
              (char *) "gzip", (char *) "-d", old_name, NULL
            };
            char *compress_argv[] = {
              (char *) "gzip", options, base, NULL
            };
            conversion_status = run_gzip_process(3, decompress_argv, -1, -1);
            if (conversion_status == 0)
              conversion_status = run_gzip_process(options[0] ? 3 : 2,
                                                    options[0]
                                                      ? compress_argv
                                                      : (char *[]){(char *) "gzip", base, NULL},
                                                    -1, -1);
          }
        if (conversion_status != 0)
          {
            if (!use_pipe && check)
              rename(backup, old_name);
            printf("error while recompressing %s\n", old_name);
            result = 1;
            continue;
          }
        if (use_pipe)
          {
            chmod(new_name, old_status.st_mode & 07777);
            {
              struct utimbuf times = {old_status.st_atime, old_status.st_mtime};
              utime(new_name, &times);
            }
          }
        if (keep && stat(new_name, &new_status) == 0
            && (old_status.st_size + 1023) / 1024
                 < (new_status.st_size + 1023) / 1024)
          {
            if (use_pipe)
              unlink(new_name);
            else
              {
                rename(backup, old_name);
                unlink(new_name);
              }
            printf("%s smaller than %s -- unchanged\n", old_name, new_name);
          }
        else if (check)
          {
            char *test_argv[] = {
              (char *) "gzip", (char *) "-t", new_name, NULL
            };
            if (run_gzip_process(3, test_argv, -1, -1) == 0)
              {
                unlink(backup);
                unlink(old_name);
              }
            else
              {
                if (!use_pipe)
                  rename(backup, old_name);
                unlink(new_name);
                printf("error while testing %s, %s unchanged\n",
                       new_name, old_name);
                result = 1;
              }
          }
        else if (use_pipe)
          unlink(old_name);
      }
    return result;
  }
}

static char const gzexe_stub[] =
  "#!/bin/bash\n"
  "skip=49\n"
  "\n"
  "tab='\t'\n"
  "nl='\n"
  "'\n"
  "IFS=\" $tab$nl\"\n"
  "\n"
  "umask=`umask`\n"
  "umask 77\n"
  "\n"
  "gztmpdir=\n"
  "trap 'res=$?\n"
  "  test -n \"$gztmpdir\" && rm -fr \"$gztmpdir\"\n"
  "  (exit $res); exit $res\n"
  "' 0 1 2 3 5 10 13 15\n"
  "\n"
  "case $TMPDIR in\n"
  "  / | /*/) ;;\n"
  "  /*) TMPDIR=$TMPDIR/;;\n"
  "  *) TMPDIR=/tmp/;;\n"
  "esac\n"
  "if command -v mktemp >/dev/null 2>&1; then\n"
  "  gztmpdir=`mktemp -d \"${TMPDIR}gztmpXXXXXXXXX\"`\n"
  "else\n"
  "  gztmpdir=${TMPDIR}gztmp$$; mkdir $gztmpdir\n"
  "fi || { (exit 127); exit 127; }\n"
  "\n"
  "gztmp=$gztmpdir/$0\n"
  "case $0 in\n"
  "-* | */*'\n"
  "') mkdir -p \"$gztmp\" && rm -r \"$gztmp\";;\n"
  "*/*) gztmp=$gztmpdir/`basename \"$0\"`;;\n"
  "esac || { (exit 127); exit 127; }\n"
  "\n"
  "case `printf 'X\\n' | tail -n +1 2>/dev/null` in\n"
  "X) tail_n=-n;;\n"
  "*) tail_n=;;\n"
  "esac\n"
  "if tail $tail_n +$skip <\"$0\" | gzip -cd > \"$gztmp\"; then\n"
  "  umask $umask\n"
  "  chmod 700 \"$gztmp\"\n"
  "  (sleep 5; rm -fr \"$gztmpdir\") 2>/dev/null &\n"
  "  \"$gztmp\" ${1+\"$@\"}; res=$?\n"
  "else\n"
  "  printf >&2 '%s\\n' \"Cannot decompress $0\"\n"
  "  (exit 127); res=127\n"
  "fi; exit $res\n";

static int
gzexe_help(char const *invocation)
{
  return printf(
    "Usage: %s [OPTION] FILE...\n"
    "Replace each executable FILE with a compressed version of itself.\n"
    "Make a backup FILE~ of the old version of FILE.\n\n"
    "  -d             Decompress each FILE instead of compressing it.\n"
    "      --help     display this help and exit\n"
    "      --version  output version information and exit\n\n"
    "Report bugs to <bug-gzip@gnu.org>.\n", invocation) < 0;
}

static int
gzexe_version(void)
{
  return printf(
    "gzexe (gzip) 1.14\n"
    "Copyright (C) 2025 Free Software Foundation, Inc.\n"
    "This is free software.  You may redistribute copies of it under the terms of\n"
    "the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n"
    "There is NO WARRANTY, to the extent permitted by law.\n\n"
    "Written by Jean-loup Gailly.\n") < 0;
}

static int
gzexe_already_wrapped(char const *name, unsigned *skip)
{
  FILE *stream = fopen(name, "r");
  char line[64];
  unsigned value;
  char extra;
  int result = 0;
  if (!stream)
    return 0;
  if (fgets(line, sizeof line, stream)
      && fgets(line, sizeof line, stream)
      && sscanf(line, "skip=%u%c", &value, &extra) == 2
      && extra == '\n' && value <= 999)
    {
      if (skip)
        *skip = value;
      result = 1;
    }
  fclose(stream);
  return result;
}

static int
gzexe_depends_on_self(char const *name)
{
  static char const *const commands[] = {
    "basename", "bash", "cat", "chmod", "cp", "dirname", "expr", "gzip",
    "ln", "mkdir", "mktemp", "mv", "printf", "rm", "sed", "sh", "sleep",
    "test", "tail", NULL
  };
  char const *base = strrchr(name, '/');
  int index;
  base = base ? base + 1 : name;
  for (index = 0; commands[index]; index++)
    if (strcmp(base, commands[index]) == 0)
      return 1;
  return 0;
}

static int
write_all(int descriptor, void const *data, size_t length)
{
  char const *position = data;
  while (length)
    {
      ssize_t count = write(descriptor, position, length);
      if (count <= 0)
        return 1;
      position += count;
      length -= (size_t) count;
    }
  return 0;
}

int
rustbox_gzexe_main(int argc, char **argv)
{
  int decompress = 0;
  int first = 1;
  int result = 0;
  int index;
  while (first < argc)
    {
      if (strcmp(argv[first], "-d") == 0)
        {
          decompress = 1;
          first++;
        }
      else if (strncmp(argv[first], "--h", 3) == 0)
        return gzexe_help(argv[0]);
      else if (strncmp(argv[first], "--v", 3) == 0)
        return gzexe_version();
      else if (strcmp(argv[first], "--") == 0)
        {
          first++;
          break;
        }
      else
        break;
    }
  if (first == argc)
    {
      fprintf(stderr, "%s: missing operand\nTry `%s --help' for more information.\n",
              argv[0], argv[0]);
      return 1;
    }
  for (index = first; index < argc; index++)
    {
      char const *argument = argv[index];
      size_t length = strlen(argument);
      char local_name[length + 3];
      char backup[length + 2];
      char temporary[length + sizeof ".gzexeXXXXXX"];
      char const *name = argument;
      struct stat status;
      unsigned skip = 44;
      int descriptor;
      int writable;
      int operation_status = 0;
      if (argument[0] == '-')
        {
          memcpy(local_name, "./", 2);
          memcpy(local_name + 2, argument, length + 1);
          name = local_name;
          length += 2;
        }
      if (stat(name, &status) != 0 || !S_ISREG(status.st_mode)
          || access(name, R_OK) != 0)
        {
          fprintf(stderr, "%s: %s is not a readable regular file\n",
                  argv[0], argument);
          continue;
        }
      if (!decompress && gzexe_already_wrapped(name, NULL))
        {
          fprintf(stderr, "%s: %s is already gzexe'd\n", argv[0], argument);
          continue;
        }
      if (status.st_mode & S_ISUID)
        {
          fprintf(stderr, "%s: %s has setuid permission, unchanged\n",
                  argv[0], argument);
          continue;
        }
      if (status.st_mode & S_ISGID)
        {
          fprintf(stderr, "%s: %s has setgid permission, unchanged\n",
                  argv[0], argument);
          continue;
        }
      if (gzexe_depends_on_self(name))
        {
          fprintf(stderr, "%s: %s might depend on itself\n", argv[0], argument);
          continue;
        }
      snprintf(temporary, sizeof temporary, "%s.gzexeXXXXXX", name);
      descriptor = mkstemp(temporary);
      if (descriptor < 0)
        {
          fprintf(stderr, "%s: cannot copy %s\n", argv[0], name);
          result = 1;
          continue;
        }
      close(descriptor);
      if (copy_regular_file(name, temporary) != 0)
        {
          unlink(temporary);
          fprintf(stderr, "%s: cannot copy %s\n", argv[0], name);
          result = 1;
          continue;
        }
      writable = (status.st_mode & S_IWUSR) != 0;
      if (!writable && chmod(temporary, status.st_mode | S_IWUSR) != 0)
        {
          unlink(temporary);
          fprintf(stderr, "%s: cannot chmod %s\n", argv[0], temporary);
          result = 1;
          continue;
        }
      descriptor = open(temporary, O_WRONLY | O_TRUNC);
      if (descriptor < 0)
        operation_status = 1;
      else if (!decompress)
        {
          char *gzip_argv[] = {
            (char *) "gzip", (char *) "-cv9", (char *) name, NULL
          };
          if (sizeof gzexe_stub - 1 != 932
              || write_all(descriptor, gzexe_stub, sizeof gzexe_stub - 1) != 0
              || run_gzip_process(3, gzip_argv, -1, descriptor) != 0)
            operation_status = 1;
        }
      else
        {
          int input = open(name, O_RDONLY);
          unsigned lines = 0;
          char byte;
          char *gzip_argv[] = {
            (char *) "gzip", (char *) "-cd", NULL
          };
          if (gzexe_already_wrapped(name, &skip))
            ;
          while (0 <= input && lines + 1 < skip && read(input, &byte, 1) == 1)
            if (byte == '\n')
              lines++;
          if (input < 0 || lines + 1 != skip
              || run_gzip_process(2, gzip_argv, input, descriptor) != 0)
            operation_status = 1;
          if (0 <= input)
            close(input);
        }
      if (0 <= descriptor)
        close(descriptor);
      if (operation_status)
        {
          unlink(temporary);
          fprintf(stderr, decompress
                  ? "%s: %s probably not in gzexe format, file unchanged.\n"
                  : "%s: compression not possible for %s, file unchanged.\n",
                  argv[0], argument);
          result = 1;
          continue;
        }
      if (!writable && chmod(temporary, status.st_mode & ~S_IWUSR) != 0)
        {
          unlink(temporary);
          fprintf(stderr, "%s: %s: cannot chmod\n", argv[0], temporary);
          result = 1;
          continue;
        }
      snprintf(backup, sizeof backup, "%s~", name);
      unlink(backup);
      if (link(name, backup) != 0 && copy_regular_file(name, backup) != 0)
        {
          unlink(temporary);
          fprintf(stderr, "%s: cannot backup %s as %s~\n",
                  argv[0], argument, argument);
          result = 1;
          continue;
        }
      if (rename(temporary, name) != 0)
        {
          unlink(temporary);
          fprintf(stderr, "%s: cannot rename %s to %s\n",
                  argv[0], temporary, argument);
          result = 1;
        }
    }
  return result;
}
