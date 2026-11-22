/* SPDX-License-Identifier: GPL-3.0-or-later */
/* In-binary replacement for GNU Findutils' installed updatedb shell driver. */

#define _GNU_SOURCE 1

#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <pwd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_coreutils_dispatch (int, char **);
extern int rustbox_find_main (int, char **);
extern int rustbox_frcode_main (int, char **);

struct words
{
  char **item;
  size_t used;
  size_t allocated;
};

static const char version_text[] =
  "\nupdatedb (GNU findutils) 4.10.0\n"
  "Copyright (C) 1994-2024 Free Software Foundation, Inc.\n"
  "License GPLv3+: GNU GPL version 3 or later <https://gnu.org/licenses/gpl.html>\n"
  "This is free software: you are free to change and redistribute it.\n"
  "There is NO WARRANTY, to the extent permitted by law.\n\n"
  "Written by Eric B. Decker, James Youngman, and Kevin Dalley.\n\n";

static void
usage (const char *name)
{
  printf ("Usage: %s [--findoptions='-option1 -option2...']\n"
          "       [--localpaths='dir1 dir2...'] [--netpaths='dir1 dir2...']\n"
          "       [--prunepaths='dir1 dir2...'] [--prunefs='fs1 fs2...']\n"
          "       [--output=dbfile] [--netuser=user] [--localuser=user]\n"
          "       [--dbformat] [--version] [--help]\n\n"
          "Please see also the documentation at https://www.gnu.org/software/findutils/.\n"
          "Report (and track progress on fixing) bugs in the updatedb\n"
          "program via the GNU findutils bug-reporting page at\n"
          "https://savannah.gnu.org/bugs/?group=findutils or, if\n"
          "you have no web access, by sending email to <bug-findutils@gnu.org>.\n\n",
          name);
}

static void
die_memory (void)
{
  fputs ("updatedb: memory exhausted\n", stderr);
  exit (1);
}

static char *
xstrdup (const char *value)
{
  char *copy = strdup (value);
  if (!copy)
    die_memory ();
  return copy;
}

static void
push (struct words *words, const char *value)
{
  if (words->used + 1 >= words->allocated)
    {
      size_t next = words->allocated ? words->allocated * 2 : 32;
      char **items = realloc (words->item, next * sizeof *items);
      if (!items)
        die_memory ();
      words->item = items;
      words->allocated = next;
    }
  words->item[words->used++] = xstrdup (value);
  words->item[words->used] = NULL;
}

static void
split (struct words *words, const char *text)
{
  const char *start;
  while (*text)
    {
      while (*text == ' ' || *text == '\t' || *text == '\n')
        ++text;
      if (!*text)
        break;
      start = text;
      while (*text && *text != ' ' && *text != '\t' && *text != '\n')
        ++text;
      {
        size_t length = (size_t) (text - start);
        char *word = malloc (length + 1);
        if (!word)
          die_memory ();
        memcpy (word, start, length);
        word[length] = 0;
        push (words, word);
        free (word);
      }
    }
}

static void
free_words (struct words *words)
{
  size_t index;
  for (index = 0; index < words->used; ++index)
    free (words->item[index]);
  free (words->item);
}

static const char *
environment_or (const char *name, const char *fallback)
{
  const char *value = getenv (name);
  return value ? value : fallback;
}

static char *
prune_regex (const char *paths)
{
  struct words words = { 0 };
  size_t index;
  size_t length = 1;
  char *result;
  split (&words, paths);
  if (!words.used)
    {
      free_words (&words);
      return xstrdup ("\\(^$\\)");
    }
  for (index = 0; index < words.used; ++index)
    length += strlen (words.item[index]) + 12;
  result = malloc (length);
  if (!result)
    die_memory ();
  result[0] = 0;
  for (index = 0; index < words.used; ++index)
    {
      if (index)
        strcat (result, "\\|" );
      strcat (result, "\\(^");
      strcat (result, words.item[index]);
      strcat (result, "$\\)");
    }
  free_words (&words);
  return result;
}

static int
switch_user (const char *name)
{
  struct passwd *account;
  if (!name || !*name || geteuid () != 0)
    return 0;
  account = getpwnam (name);
  if (!account)
    return -1;
  if (initgroups (account->pw_name, account->pw_gid) != 0
      || setgid (account->pw_gid) != 0
      || setuid (account->pw_uid) != 0)
    return -1;
  return 0;
}

static int
wait_status (pid_t process)
{
  int status;
  while (waitpid (process, &status, 0) < 0)
    if (errno != EINTR)
      return 1;
  if (WIFEXITED (status))
    return WEXITSTATUS (status);
  return WIFSIGNALED (status) ? 128 + WTERMSIG (status) : 1;
}

static void
close_extra_descriptors (void)
{
  long limit = sysconf (_SC_OPEN_MAX);
  int descriptor;
  if (limit < 0 || limit > 65536)
    limit = 65536;
  for (descriptor = 3; descriptor < limit; ++descriptor)
    close (descriptor);
}

static int
run_find (const char *paths, const char *find_options, const char *prune_fses,
          const char *regex, const char *user)
{
  struct words arguments = { 0 };
  struct words path_words = { 0 };
  struct words option_words = { 0 };
  struct words fs_words = { 0 };
  size_t index;
  int result;
  split (&path_words, paths);
  if (!path_words.used)
    {
      free_words (&path_words);
      return 0;
    }
  split (&option_words, find_options);
  split (&fs_words, prune_fses);
  push (&arguments, "find");
  for (index = 0; index < path_words.used; ++index)
    push (&arguments, path_words.item[index]);
  for (index = 0; index < option_words.used; ++index)
    push (&arguments, option_words.item[index]);
  push (&arguments, "(");
  for (index = 0; index < fs_words.used; ++index)
    {
      push (&arguments, "-fstype");
      push (&arguments, fs_words.item[index]);
      push (&arguments, "-o");
    }
  push (&arguments, "-type");
  push (&arguments, "d");
  push (&arguments, "-regex");
  push (&arguments, regex);
  push (&arguments, ")");
  push (&arguments, "-prune");
  push (&arguments, "-o");
  push (&arguments, "-print0");
  if (switch_user (user) != 0)
    {
      fprintf (stderr, "updatedb: cannot become user %s\n", user);
      result = 1;
    }
  else
    {
      program_invocation_name = arguments.item[0];
      program_invocation_short_name = arguments.item[0];
      result = rustbox_find_main ((int) arguments.used, arguments.item);
      fflush (NULL);
    }
  free_words (&arguments);
  free_words (&path_words);
  free_words (&option_words);
  free_words (&fs_words);
  return result;
}

static int
run_find_isolated (const char *paths, const char *find_options,
                   const char *prune_fses, const char *regex,
                   const char *user)
{
  pid_t child;
  if (!paths || !*paths)
    return 0;
  child = fork ();
  if (child < 0)
    return 1;
  if (child == 0)
    exit (run_find (paths, find_options, prune_fses, regex, user));
  return wait_status (child);
}

static pid_t
spawn_find_producer (int output, const char *directory,
                     const char *local_paths, const char *network_paths,
                     const char *find_options, const char *prune_fses,
                     const char *regex, const char *local_user,
                     const char *network_user)
{
  pid_t child = fork ();
  if (child == 0)
    {
      int local_status;
      int network_status;
      if (dup2 (output, STDOUT_FILENO) < 0)
        _exit (1);
      close_extra_descriptors ();
      if (chdir (directory) != 0)
        _exit (1);
      local_status = run_find_isolated (local_paths, find_options, prune_fses,
                                        regex, local_user);
      network_status = run_find_isolated (
        network_paths, find_options, "", regex,
        geteuid () == 0 ? network_user : "");
      exit (local_status ? local_status : network_status);
    }
  return child;
}

static pid_t
spawn_sort (int input, int output)
{
  pid_t child = fork ();
  if (child == 0)
    {
      char *arguments[] = { (char *) "sort", (char *) "-z", NULL };
      if (dup2 (input, STDIN_FILENO) < 0 || dup2 (output, STDOUT_FILENO) < 0)
        _exit (1);
      close_extra_descriptors ();
      program_invocation_name = arguments[0];
      program_invocation_short_name = arguments[0];
      exit (rustbox_coreutils_dispatch (2, arguments));
    }
  return child;
}

static pid_t
spawn_frcode (int input, int output, int slocate)
{
  pid_t child = fork ();
  if (child == 0)
    {
      char *normal[] = { (char *) "frcode", (char *) "-0", NULL };
      char *secure[] = {
        (char *) "frcode", (char *) "-S", (char *) "1", (char *) "-0", NULL
      };
      char **arguments = slocate ? secure : normal;
      int count = slocate ? 4 : 2;
      if (dup2 (input, STDIN_FILENO) < 0 || dup2 (output, STDOUT_FILENO) < 0)
        _exit (1);
      close_extra_descriptors ();
      program_invocation_name = arguments[0];
      program_invocation_short_name = arguments[0];
      exit (rustbox_frcode_main (count, arguments));
    }
  return child;
}

int
rustbox_updatedb_main (int argc, char **argv)
{
  const char *name = argv[0];
  const char *find_options = environment_or ("FINDOPTIONS", "");
  const char *local_paths = environment_or ("SEARCHPATHS", "/");
  const char *network_paths = environment_or ("NETPATHS", "");
  const char *prune_paths = environment_or (
    "PRUNEPATHS", "/afs\n/amd\n/proc\n/sfs\n/tmp\n/usr/tmp\n/var/tmp");
  const char *prune_fses = environment_or (
    "PRUNEFS", "9P NFS afs autofs cifs coda devfs devpts ftpfs fuse.s3fs "
    "iso9660 mfs ncpfs nfs nfs4 proc shfs smbfs sysfs");
  const char *database = environment_or ("LOCATE_DB", "/var/lib/locatedb");
  const char *network_user = environment_or ("NETUSER", "daemon");
  const char *local_user = environment_or ("LOCALUSER", "");
  const char *directory = "/";
  const char *format = "";
  const char *explicit_regex = getenv ("PRUNEREGEX");
  char *regex;
  char *temporary;
  int first_pipe[2];
  int second_pipe[2];
  int output;
  int index;
  int slocate = 0;
  pid_t producer;
  pid_t sorter;
  pid_t encoder;
  int producer_status;
  int sorter_status;
  int encoder_status;
  struct stat information;

  if (setenv ("LC_ALL", "C", 1) != 0)
    {
      perror ("updatedb");
      return 1;
    }

  for (index = 1; index < argc; ++index)
    {
      char *equals = strchr (argv[index], '=');
      size_t option_length = equals ? (size_t) (equals - argv[index]) : strlen (argv[index]);
      const char *value = equals ? equals + 1 : argv[index];
#define OPTION(text) (option_length == sizeof (text) - 1 && !memcmp (argv[index], text, sizeof (text) - 1))
      if (OPTION ("--findoptions")) find_options = value;
      else if (OPTION ("--localpaths")) local_paths = value;
      else if (OPTION ("--netpaths")) network_paths = value;
      else if (OPTION ("--prunepaths")) prune_paths = value;
      else if (OPTION ("--prunefs")) prune_fses = value;
      else if (OPTION ("--output")) database = value;
      else if (OPTION ("--netuser")) network_user = value;
      else if (OPTION ("--localuser")) local_user = value;
      else if (OPTION ("--changecwd")) directory = value;
      else if (OPTION ("--dbformat")) format = value;
      else if (OPTION ("--version"))
        return fputs (version_text, stdout) == EOF;
      else if (OPTION ("--help"))
        {
          usage (name);
          return ferror (stdout) != 0;
        }
      else
        {
          fprintf (stderr, "updatedb: invalid option %.*s\n"
                   "Try '%s --help' for more information.\n",
                   (int) option_length, argv[index], name);
          return 1;
        }
#undef OPTION
    }

  if (!*format || !strcmp (format, "LOCATE02"))
    slocate = 0;
  else if (!strcmp (format, "slocate"))
    slocate = 1;
  else
    {
      fprintf (stderr,
               "Unsupported locate database format %s: Supported formats are:\n"
               "LOCATE02, slocate\n", format);
      return 1;
    }

  {
    struct words paths = { 0 };
    size_t item;
    split (&paths, prune_paths);
    for (item = 0; item < paths.used; ++item)
      {
        size_t length = strlen (paths.item[item]);
        if (length > 1 && paths.item[item][length - 1] == '/')
          {
            fprintf (stderr, "%s: %s: pruned paths should not contain trailing slashes\n",
                     name, paths.item[item]);
            free_words (&paths);
            return 1;
          }
      }
    free_words (&paths);
  }
  regex = explicit_regex && *explicit_regex ? xstrdup (explicit_regex)
                                           : prune_regex (prune_paths);
  temporary = malloc (strlen (database) + 3);
  if (!temporary)
    die_memory ();
  sprintf (temporary, "%s.n", database);
  unlink (temporary);
  output = open (temporary, O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (output < 0 || pipe (first_pipe) != 0 || pipe (second_pipe) != 0)
    {
      perror ("updatedb");
      free (regex);
      free (temporary);
      if (output >= 0) close (output);
      return 1;
    }

  producer = spawn_find_producer (first_pipe[1], directory, local_paths,
                                  network_paths, find_options, prune_fses,
                                  regex, local_user, network_user);
  sorter = spawn_sort (first_pipe[0], second_pipe[1]);
  encoder = spawn_frcode (second_pipe[0], output, slocate);
  close (first_pipe[0]);
  close (first_pipe[1]);
  close (second_pipe[0]);
  close (second_pipe[1]);
  close (output);
  producer_status = producer < 0 ? 1 : wait_status (producer);
  sorter_status = sorter < 0 ? 1 : wait_status (sorter);
  encoder_status = encoder < 0 ? 1 : wait_status (encoder);
  free (regex);
  if (producer_status || sorter_status || encoder_status)
    {
      int status = producer_status ? producer_status
                   : sorter_status ? sorter_status : encoder_status;
      fprintf (stderr, "Failed to generate %s\n", temporary);
      unlink (temporary);
      free (temporary);
      return status;
    }
  if (stat (temporary, &information) == 0 && information.st_size > 0)
    {
      if (chmod (temporary, 0644) != 0 || rename (temporary, database) != 0)
        {
          perror ("updatedb");
          unlink (temporary);
          free (temporary);
          return 1;
        }
    }
  else
    {
      fputs ("updatedb: new database would be empty\n", stderr);
      unlink (temporary);
    }
  free (temporary);
  return 0;
}
