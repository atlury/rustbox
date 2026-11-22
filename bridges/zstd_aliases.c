/* SPDX-License-Identifier: BSD-2-Clause
   Native equivalents of zstd 1.5.7's installed shell frontends. */
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_zstd_main(int, char **);
extern int rustbox_grep_main(int, char **);
extern int rustbox_less_main(int, char **);

typedef int (*applet_main)(int, char **);

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
start_zstd(const char *name, int output, int close_fd)
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
		char *zstd_argv[] = {
			(char *)"zstd", (char *)"-cdfq", (char *)"--", (char *)name, NULL
		};
		int status;
		program_invocation_name = zstd_argv[0];
		program_invocation_short_name = zstd_argv[0];
		status = rustbox_zstd_main(4, zstd_argv);
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
grep_one(const char *file, char **arguments, int argument_count)
{
	int pipe_fd[2];
	pid_t zstd_child;
	pid_t grep_child;
	int grep_status;
	int zstd_status;
	if (pipe(pipe_fd) < 0)
		return 2;
	zstd_child = start_zstd(file, pipe_fd[1], pipe_fd[0]);
	if (zstd_child < 0) {
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
	zstd_status = wait_child(zstd_child);
	if (zstd_status != 0 && zstd_status != 128 + SIGPIPE)
		return 2;
	return grep_status;
}

int
rustbox_zstdgrep_main(int argc, char **argv)
{
	char *grep_argv[argc + 9];
	char *files[argc + 1];
	char *pattern = NULL;
	int grep_argc = 1;
	int file_count = 0;
	int pattern_found = 0;
	int hyphen = 0;
	int silent = 0;
	int index = 1;
	int result = 0;
	grep_argv[0] = (char *)"grep";

	while (index < argc) {
		char *argument = argv[index];
		if (strcmp(argument, "--") == 0) {
			index++;
			break;
		}
		if (strcmp(argument, "-") == 0) {
			hyphen = 1;
			index++;
			continue;
		}
		if (strcmp(argument, "-h") == 0) {
			silent = 1;
			index++;
			continue;
		}
		if (argument[0] != '-')
			break;
		if (strlen(argument) == 2 && strchr("ABCDXdefm", argument[1])) {
			if (index + 1 >= argc) {
				fprintf(stderr, "zstdgrep: missing argument for %s flag\n", argument);
				return 1;
			}
			grep_argv[grep_argc++] = argument;
			grep_argv[grep_argc++] = argv[index + 1];
			if (argument[1] == 'e') {
				pattern = argv[index + 1];
				pattern_found = 1;
				index += 2;
				break;
			}
			if (argument[1] == 'f')
				pattern_found = 2;
			index += 2;
			continue;
		}
		grep_argv[grep_argc++] = argument;
		index++;
	}
	if (pattern_found == 0) {
		if (index < argc)
			pattern = argv[index++];
		else if (hyphen)
			pattern = (char *)"-";
		else {
			fputs("zstdgrep: missing pattern\n", stderr);
			return 1;
		}
	}
	while (index < argc)
		files[file_count++] = argv[index++];
	if (file_count == 0)
		files[file_count++] = (char *)"-";
	for (index = 0; index < file_count; ++index) {
		int local_argc = grep_argc;
		int status;
		char label[strlen(files[index]) + sizeof "--label="];
		if (!silent && file_count > 1)
			grep_argv[local_argc++] = (char *)"-H";
		snprintf(label, sizeof label, "--label=%s", files[index]);
		grep_argv[local_argc++] = label;
		grep_argv[local_argc++] = (char *)"--";
		if (pattern_found != 2)
			grep_argv[local_argc++] = pattern;
		grep_argv[local_argc++] = (char *)"-";
		grep_argv[local_argc] = NULL;
		status = grep_one(files[index], grep_argv, local_argc);
		if (status != 0)
			result = 1;
	}
	return result;
}

static int
copy_decompressed(const char *file)
{
	pid_t child = start_zstd(file, STDOUT_FILENO, -1);
	return child < 0 ? 2 : wait_child(child);
}

int
rustbox_zstdless_main(int argc, char **argv)
{
	int index;
	int status = 0;
	if (argc > 1 &&
	    (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "--version") == 0)) {
		argv[0] = (char *)"less";
		program_invocation_name = argv[0];
		program_invocation_short_name = argv[0];
		return rustbox_less_main(argc, argv);
	}
	if (!isatty(STDOUT_FILENO)) {
		if (argc == 1)
			return copy_decompressed("-");
		for (index = 1; index < argc; ++index) {
			if (argv[index][0] == '-' && strcmp(argv[index], "-") != 0)
				continue;
			status = copy_decompressed(argv[index]);
			if (status != 0)
				return status;
		}
		return status;
	}
	if (argc == 1) {
		char *less_argv[] = {(char *)"less", NULL};
		return rustbox_less_main(1, less_argv);
	}
	for (index = 1; index < argc; ++index) {
		int pipe_fd[2];
		pid_t zstd_child;
		pid_t less_child;
		char *less_argv[] = {(char *)"less", NULL};
		if (argv[index][0] == '-' && strcmp(argv[index], "-") != 0)
			continue;
		if (pipe(pipe_fd) < 0)
			return 2;
		zstd_child = start_zstd(argv[index], pipe_fd[1], pipe_fd[0]);
		close(pipe_fd[1]);
		less_child = start_applet(rustbox_less_main, 1, less_argv, pipe_fd[0], -1);
		close(pipe_fd[0]);
		if (zstd_child < 0 || less_child < 0)
			return 2;
		status = wait_child(less_child);
		if (wait_child(zstd_child) != 0)
			return 2;
		if (status != 0)
			return status;
	}
	return status;
}
