/* SPDX-License-Identifier: GPL-2.0-or-later
   Native equivalents of XZ Utils 5.8.4's installed shell frontends. */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_xz_main(int, char **);
extern int rustbox_cmp_main(int, char **);
extern int rustbox_diff_main(int, char **);
extern int rustbox_grep_main(int, char **);
extern int rustbox_less_main(int, char **);
extern int rustbox_more_main(int, char **);

typedef int (*applet_main)(int, char **);

static const char *
base_name(const char *path)
{
	const char *slash = strrchr(path, '/');
	return slash == NULL ? path : slash + 1;
}

static int
wait_child(pid_t child)
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

static pid_t
start_xz(const char *name, int output, int close_fd)
{
	pid_t child;
	fflush(NULL);
	child = fork();
	if (child != 0)
		return child;
	if (output != STDOUT_FILENO) {
		if (dup2(output, STDOUT_FILENO) < 0)
			_exit(2);
		close(output);
	}
	if (close_fd >= 0)
		close(close_fd);
	{
		char *xz_argv[] = {
			(char *)"xz", (char *)"--format=auto", (char *)"-cdfqQ",
			(char *)"--", (char *)name, NULL
		};
		int status;
		program_invocation_name = xz_argv[0];
		program_invocation_short_name = xz_argv[0];
		status = rustbox_xz_main(5, xz_argv);
		fflush(NULL);
		_exit(status);
	}
}

static pid_t
start_applet(applet_main main_fn, int argc, char **argv, int input, int close_fd)
{
	pid_t child;
	fflush(NULL);
	child = fork();
	if (child != 0)
		return child;
	if (input != STDIN_FILENO) {
		if (dup2(input, STDIN_FILENO) < 0)
			_exit(2);
		close(input);
	}
	if (close_fd >= 0)
		close(close_fd);
	program_invocation_name = argv[0];
	program_invocation_short_name = argv[0];
	{
		int status = main_fn(argc, argv);
		fflush(NULL);
		_exit(status);
	}
}

static int
decompress_to_file(const char *name, char template_name[])
{
	int fd = mkstemp(template_name);
	pid_t child;
	int status;
	if (fd < 0)
		return 2;
	child = start_xz(name, fd, -1);
	close(fd);
	if (child < 0) {
		unlink(template_name);
		return 2;
	}
	status = wait_child(child);
	if (status != 0) {
		unlink(template_name);
		return 2;
	}
	return 0;
}

static int
is_compressed(const char *name)
{
	static const char *const suffixes[] = {
		".xz", "-xz", ".lzma", "-lzma", ".lz", "-lz", ".txz", ".tlz"
	};
	size_t length = strlen(name);
	size_t index;
	if (strcmp(name, "-") == 0)
		return 1;
	for (index = 0; index < sizeof suffixes / sizeof suffixes[0]; ++index) {
		size_t suffix_length = strlen(suffixes[index]);
		if (length >= suffix_length
		    && strcmp(name + length - suffix_length, suffixes[index]) == 0)
			return 1;
	}
	return 0;
}

static char *
uncompressed_name(const char *name)
{
	size_t length = strlen(name);
	size_t remove = 0;
	char *result;
	if (length >= 4 && strcmp(name + length - 4, ".txz") == 0)
		remove = 2;
	else if (length >= 4 && strcmp(name + length - 4, ".tlz") == 0)
		remove = 2;
	else if (length >= 5 && strcmp(name + length - 5, ".lzma") == 0)
		remove = 5;
	else if (length >= 3 && strcmp(name + length - 3, ".xz") == 0)
		remove = 3;
	else if (length >= 3 && strcmp(name + length - 3, ".lz") == 0)
		remove = 3;
	if (remove == 0)
		return NULL;
	result = malloc(length - remove + (remove == 2 ? 3 : 1));
	if (result == NULL)
		return NULL;
	memcpy(result, name, length - remove);
	if (remove == 2) {
		result[length - remove] = 'a';
		result[length - remove + 1] = 'r';
		result[length - remove + 2] = '\0';
	} else
		result[length - remove] = '\0';
	return result;
}

static int
print_diff_help(const char *name, const char *compare)
{
	return printf(
		"Usage: %s [OPTION]... FILE1 [FILE2]\n"
		"Compare FILE1 to FILE2, using their uncompressed contents if they are\n"
		"compressed.  If FILE2 is omitted, then the files compared are FILE1 and\n"
		"FILE1 from which the compression format suffix has been stripped.\n\n"
		"Do comparisons like '%s' does.  OPTIONs are the same as for '%s'.\n\n"
		"Report bugs to <xz@tukaani.org>.\n", name, compare, compare) < 0 ? 2 : 0;
}

int
rustbox_xzdiff_main(int argc, char **argv)
{
	const char *invoked = base_name(argv[0]);
	int use_cmp = strstr(invoked, "cmp") != NULL;
	const char *version_name = use_cmp ? "xzcmp" : "xzdiff";
	applet_main compare_main = use_cmp ? rustbox_cmp_main : rustbox_diff_main;
	const char *compare = use_cmp ? "cmp" : "diff";
	char *compare_argv[argc + 2];
	const char *files[2] = {NULL, NULL};
	char *derived = NULL;
	char first_tmp[] = "/tmp/rustbox-xzdiff-1-XXXXXX";
	char second_tmp[] = "/tmp/rustbox-xzdiff-2-XXXXXX";
	const char *first_path;
	const char *second_path;
	int compare_argc = 1;
	int file_count = 0;
	int index;
	int status;

	for (index = 1; index < argc; ++index) {
		if (strncmp(argv[index], "--h", 3) == 0)
			return print_diff_help(invoked, compare);
		if (strncmp(argv[index], "--v", 3) == 0)
			return printf("%s (XZ Utils) 5.8.4\n", version_name) < 0 ? 2 : 0;
		if (argv[index][0] == '-' && strcmp(argv[index], "-") != 0) {
			compare_argv[compare_argc++] = argv[index];
			continue;
		}
		if (file_count == 2) {
			fprintf(stderr, "%s: Invalid number of operands; try '%s --help' for help\n",
			        invoked, invoked);
			return 2;
		}
		files[file_count++] = argv[index];
	}
	if (file_count == 1) {
		derived = uncompressed_name(files[0]);
		if (derived == NULL) {
			fprintf(stderr, "%s: %s: Unknown compressed file name suffix\n",
			        invoked, files[0]);
			return 2;
		}
		files[1] = derived;
		file_count = 2;
	}
	if (file_count != 2) {
		fprintf(stderr, "%s: Invalid number of operands; try '%s --help' for help\n",
		        invoked, invoked);
		free(derived);
		return 2;
	}
	first_path = files[0];
	second_path = files[1];
	if (is_compressed(files[0])) {
		if (decompress_to_file(files[0], first_tmp) != 0) {
			free(derived);
			return 2;
		}
		first_path = first_tmp;
	}
	if (is_compressed(files[1])) {
		if (decompress_to_file(files[1], second_tmp) != 0) {
			if (first_path == first_tmp)
				unlink(first_tmp);
			free(derived);
			return 2;
		}
		second_path = second_tmp;
	}
	compare_argv[0] = (char *)compare;
	compare_argv[compare_argc++] = (char *)first_path;
	compare_argv[compare_argc++] = (char *)second_path;
	compare_argv[compare_argc] = NULL;
	program_invocation_name = compare_argv[0];
	program_invocation_short_name = compare_argv[0];
	status = compare_main(compare_argc, compare_argv);
	if (first_path == first_tmp)
		unlink(first_tmp);
	if (second_path == second_tmp)
		unlink(second_tmp);
	free(derived);
	return status;
}

static int
print_grep_help(const char *name, const char *grep_name)
{
	return printf(
		"Usage: %s [OPTION]... [-e] PATTERN [FILE]...\n"
		"Look for instances of PATTERN in the input FILEs, using their\n"
		"uncompressed contents if they are compressed.\n\n"
		"OPTIONs are the same as for '%s'.\n\n"
		"Report bugs to <xz@tukaani.org>.\n", name, grep_name) < 0 ? 2 : 0;
}

static int
grep_one(const char *file, char **arguments, int argument_count)
{
	int pipe_fd[2];
	pid_t xz_child;
	pid_t grep_child;
	int grep_status;
	int xz_status;
	if (pipe(pipe_fd) < 0)
		return 2;
	xz_child = start_xz(file, pipe_fd[1], pipe_fd[0]);
	if (xz_child < 0) {
		close(pipe_fd[0]);
		close(pipe_fd[1]);
		return 2;
	}
	close(pipe_fd[1]);
	grep_child = start_applet(
		rustbox_grep_main, argument_count, arguments, pipe_fd[0], -1);
	close(pipe_fd[0]);
	if (grep_child < 0)
		return 2;
	grep_status = wait_child(grep_child);
	xz_status = wait_child(xz_child);
	if (xz_status != 0 && xz_status != 128 + SIGPIPE)
		return 2;
	return grep_status;
}

int
rustbox_xzgrep_main(int argc, char **argv)
{
	const char *invoked = base_name(argv[0]);
	int extended = strstr(invoked, "egrep") != NULL;
	int fixed = strstr(invoked, "fgrep") != NULL;
	const char *version_name = extended ? "xzegrep" : fixed ? "xzfgrep" : "xzgrep";
	char *grep_argv[argc + 8];
	int grep_argc = 1;
	int pattern_index = -1;
	int no_filename = 0;
	int with_filename = 0;
	int list_filenames = 0;
	int index;
	int result = 1;
	grep_argv[0] = (char *)"grep";
	if (extended)
		grep_argv[grep_argc++] = (char *)"-E";
	else if (fixed)
		grep_argv[grep_argc++] = (char *)"-F";
	for (index = 1; index < argc; ++index) {
		if (strcmp(argv[index], "--help") == 0)
			return print_grep_help(invoked, extended ? "grep -E" : fixed ? "grep -F" : "grep");
		if (strcmp(argv[index], "--version") == 0)
			return printf("%s (XZ Utils) 5.8.4\n", version_name) < 0 ? 2 : 0;
		if (pattern_index < 0 && argv[index][0] == '-' && strcmp(argv[index], "-") != 0) {
			if (strcmp(argv[index], "-h") == 0
			    || strcmp(argv[index], "--no-filename") == 0)
				no_filename = 1;
			if (strcmp(argv[index], "-H") == 0
			    || strcmp(argv[index], "--with-filename") == 0)
				with_filename = 1;
			if (strcmp(argv[index], "-l") == 0 || strcmp(argv[index], "-L") == 0
			    || strncmp(argv[index], "--files-with", 12) == 0)
				list_filenames = 1;
			grep_argv[grep_argc++] = argv[index];
			if ((strcmp(argv[index], "-e") == 0 || strcmp(argv[index], "--regexp") == 0)
			    && index + 1 < argc)
				grep_argv[grep_argc++] = argv[++index];
			continue;
		}
		pattern_index = index;
		break;
	}
	if (pattern_index < 0) {
		fprintf(stderr, "%s: Missing pattern; try '%s --help' for help\n", invoked, invoked);
		return 2;
	}
	grep_argv[grep_argc++] = (char *)"-e";
	grep_argv[grep_argc++] = argv[pattern_index];
	if (pattern_index + 1 == argc) {
		grep_argv[grep_argc] = NULL;
		return grep_one("-", grep_argv, grep_argc);
	}
	for (index = pattern_index + 1; index < argc; ++index) {
		int status;
		int local_argc = grep_argc;
		if ((with_filename || list_filenames
		     || (argc - pattern_index - 1 > 1 && !no_filename))
		    && strcmp(argv[index], "-") != 0) {
			grep_argv[local_argc++] = (char *)"-H";
			grep_argv[local_argc++] = (char *)"--label";
			grep_argv[local_argc++] = argv[index];
		}
		grep_argv[local_argc] = NULL;
		status = grep_one(argv[index], grep_argv, local_argc);
		if (status >= 2)
			result = status;
		else if (status == 0 && result == 1)
			result = 0;
	}
	return result;
}

static int
copy_decompressed(const char *file)
{
	pid_t child = start_xz(file, STDOUT_FILENO, -1);
	return child < 0 ? 2 : wait_child(child);
}

static int
run_pager(const char *file, int use_less)
{
	int pipe_fd[2];
	pid_t xz_child;
	pid_t pager_child;
	char *less_argv[] = {(char *)"less", NULL};
	char *more_argv[] = {(char *)"more", NULL};
	int pager_status;
	int xz_status;
	if (!isatty(STDOUT_FILENO))
		return copy_decompressed(file);
	if (pipe(pipe_fd) < 0)
		return 2;
	xz_child = start_xz(file, pipe_fd[1], pipe_fd[0]);
	close(pipe_fd[1]);
	pager_child = start_applet(
		use_less ? rustbox_less_main : rustbox_more_main, 1,
		use_less ? less_argv : more_argv, pipe_fd[0], -1);
	close(pipe_fd[0]);
	if (xz_child < 0 || pager_child < 0)
		return 2;
	pager_status = wait_child(pager_child);
	xz_status = wait_child(xz_child);
	return xz_status == 0 ? pager_status : 2;
}

static int
pager_main(int argc, char **argv, int use_less)
{
	const char *invoked = base_name(argv[0]);
	int index;
	int status = 0;
	if (argc > 1 && strcmp(argv[1], "--help") == 0) {
		if (use_less)
			return printf(
				"Usage: %s [OPTION]... [FILE]...\n"
				"Like 'less', but operate on the uncompressed contents of xz compressed FILEs.\n\n"
				"Options are the same as for 'less'.\n\n"
				"Report bugs to <xz@tukaani.org>.\n", invoked) < 0 ? 2 : 0;
		return printf(
			"Usage: %s [OPTION]... [FILE]...\n"
			"Like 'more', but operate on the uncompressed contents of xz compressed FILEs.\n\n"
			"Report bugs to <xz@tukaani.org>.\n", invoked) < 0 ? 2 : 0;
	}
	if (argc > 1 && strcmp(argv[1], "--version") == 0)
		return printf("xz%s (XZ Utils) 5.8.4\n", use_less ? "less" : "more") < 0 ? 2 : 0;
	if (argc == 1)
		return run_pager("-", use_less);
	for (index = 1; index < argc; ++index) {
		if (argv[index][0] == '-' && strcmp(argv[index], "-") != 0)
			continue;
		if (!use_less && printf("------> %s <------\n", argv[index]) < 0)
			return 2;
		status = run_pager(argv[index], use_less);
		if (status != 0)
			return status;
	}
	return status;
}

int
rustbox_xzless_main(int argc, char **argv)
{
	return pager_main(argc, argv, 1);
}

int
rustbox_xzmore_main(int argc, char **argv)
{
	return pager_main(argc, argv, 0);
}
