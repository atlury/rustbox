/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Native frontends for E2fsprogs' four installed shell programs. */

#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define E2FSPROGS_VERSION "1.47.4"
#define E2FSPROGS_DATE "6-Mar-2025"
#define SCRUB_DRY_RUN 1
#define SCRUB_REAP 2
#define SCRUB_TRIM 4
#define SCRUB_ALL 8

extern const unsigned char rustbox_e2fs_et_h_awk[];
extern const size_t rustbox_e2fs_et_h_awk_len;
extern const unsigned char rustbox_e2fs_et_c_awk[];
extern const size_t rustbox_e2fs_et_c_awk_len;
extern const unsigned char rustbox_e2fs_ct_c_sed[];
extern const size_t rustbox_e2fs_ct_c_sed_len;
extern const unsigned char rustbox_e2fs_ct_c_awk[];
extern const size_t rustbox_e2fs_ct_c_awk_len;

extern int rustbox_gawk_main(int, char **) __attribute__((weak));
extern int rustbox_sed_main(int, char **) __attribute__((weak));
extern int rustbox_lsblk_main(int, char **) __attribute__((weak));
extern int rustbox_e2fsprogs_dumpe2fs_main(int, char **) __attribute__((weak));
extern int rustbox_e2fsprogs_e2fsck_main(int, char **) __attribute__((weak));
extern int rustbox_e2fsprogs_tune2fs_main(int, char **) __attribute__((weak));

typedef int (*applet_main)(int, char **);

static const char *
base_name(const char *path)
{
	const char *slash = strrchr(path == NULL ? "" : path, '/');
	return slash == NULL ? path : slash + 1;
}

static int
wait_status(pid_t child)
{
	int status;
	if (child < 0 || waitpid(child, &status, 0) < 0)
		return 127;
	if (WIFEXITED(status))
		return WEXITSTATUS(status);
	return WIFSIGNALED(status) ? 128 + WTERMSIG(status) : 127;
}

static int
run_program(applet_main callback, const char *external, char **arguments,
    int input_fd, int output_fd)
{
	fflush(NULL);
	pid_t child = fork();
	if (child == 0) {
		int count = 0;
		if (input_fd >= 0 && input_fd != STDIN_FILENO)
			dup2(input_fd, STDIN_FILENO);
		if (output_fd >= 0 && output_fd != STDOUT_FILENO)
			dup2(output_fd, STDOUT_FILENO);
		while (arguments[count] != NULL)
			count++;
		setenv("LC_ALL", "C", 1);
		setenv("LANG", "C", 1);
		setenv("PATH", "/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin", 1);
		if (callback != NULL) {
			int status = callback(count, arguments);
			fflush(NULL);
			_exit(status);
		}
		execvp(external, arguments);
		_exit(127);
	}
	return wait_status(child);
}

static int
write_all(int descriptor, const unsigned char *data, size_t length)
{
	while (length > 0) {
		ssize_t count = write(descriptor, data, length);
		if (count < 0) {
			if (errno == EINTR)
				continue;
			return -1;
		}
		data += count;
		length -= (size_t) count;
	}
	return 0;
}

static int
write_template(const char *directory, const char *name,
    const unsigned char *data, size_t length)
{
	char path[PATH_MAX];
	int descriptor;
	if (snprintf(path, sizeof path, "%s/%s", directory, name) >=
	    (int) sizeof path)
		return -1;
	descriptor = open(path, O_WRONLY | O_CREAT | O_EXCL, 0400);
	if (descriptor < 0)
		return -1;
	if (write_all(descriptor, data, length) != 0 || close(descriptor) != 0) {
		close(descriptor);
		unlink(path);
		return -1;
	}
	return 0;
}

static int
embedded_templates(char *directory, size_t capacity, int error_tables)
{
	const char *temporary = getenv("TMPDIR");
	int failed = 0;
	if (temporary == NULL || *temporary == '\0')
		temporary = "/tmp";
	if (snprintf(directory, capacity, "%s/rustbox-e2fs-templates-XXXXXX",
	    temporary) >= (int) capacity || mkdtemp(directory) == NULL)
		return -1;
	if (error_tables) {
		if (write_template(directory, "et_h.awk", rustbox_e2fs_et_h_awk,
		    rustbox_e2fs_et_h_awk_len) != 0 ||
		    write_template(directory, "et_c.awk", rustbox_e2fs_et_c_awk,
		    rustbox_e2fs_et_c_awk_len) != 0)
			failed = 1;
	} else if (write_template(directory, "ct_c.sed", rustbox_e2fs_ct_c_sed,
	    rustbox_e2fs_ct_c_sed_len) != 0 ||
	    write_template(directory, "ct_c.awk", rustbox_e2fs_ct_c_awk,
	    rustbox_e2fs_ct_c_awk_len) != 0)
		failed = 1;
	if (failed) {
		char path[PATH_MAX];
		const char *const names[] = {"et_h.awk", "et_c.awk", "ct_c.sed", "ct_c.awk"};
		for (size_t index = 0; index < sizeof names / sizeof names[0]; index++) {
			snprintf(path, sizeof path, "%s/%s", directory, names[index]);
			unlink(path);
		}
		rmdir(directory);
		return -1;
	}
	return 0;
}

static void
remove_templates(const char *directory, int error_tables)
{
	char path[PATH_MAX];
	const char *const names_et[] = {"et_h.awk", "et_c.awk"};
	const char *const names_ss[] = {"ct_c.sed", "ct_c.awk"};
	const char *const *names = error_tables ? names_et : names_ss;
	int index;
	for (index = 0; index < 2; index++) {
		snprintf(path, sizeof path, "%s/%s", directory, names[index]);
		unlink(path);
	}
	rmdir(directory);
}

static char *
generator_root(const char *input, const char *suffix)
{
	size_t length = strlen(input);
	char *root = strdup(input);
	if (root != NULL && length >= 3 &&
	    strcmp(input + length - 2, suffix) == 0)
		root[length - 3] = '\0';
	return root;
}

static char *
append_text(const char *left, const char *right)
{
	char *result;
	if (asprintf(&result, "%s%s", left, right) < 0)
		return NULL;
	return result;
}

static int
files_equal(const char *left, const char *right)
{
	unsigned char a[8192], b[8192];
	int left_fd = open(left, O_RDONLY), right_fd = open(right, O_RDONLY);
	int equal = left_fd >= 0 && right_fd >= 0;
	while (equal) {
		ssize_t na = read(left_fd, a, sizeof a);
		ssize_t nb = read(right_fd, b, sizeof b);
		if (na != nb || na < 0 || (na > 0 && memcmp(a, b, (size_t) na) != 0))
			equal = 0;
		if (na <= 0)
			break;
	}
	if (left_fd >= 0)
		close(left_fd);
	if (right_fd >= 0)
		close(right_fd);
	return equal;
}

static int
publish_generated(const char *temporary, const char *output)
{
	struct stat status;
	if (access(output, F_OK) == 0 && files_equal(temporary, output))
		return unlink(temporary);
	if (rename(temporary, output) != 0 || stat(output, &status) != 0)
		return -1;
	return chmod(output, status.st_mode & ~(mode_t) 0222);
}

int
rustbox_e2fsprogs_compile_et_main(int argc, char **argv)
{
	char embedded[PATH_MAX] = "", h_template[PATH_MAX], c_template[PATH_MAX];
	char h_temporary[PATH_MAX] = "", c_temporary[PATH_MAX] = "";
	char *root = NULL, *source = NULL;
	char h_variable[PATH_MAX + 16], c_variable[PATH_MAX + 16];
	char h_name[PATH_MAX], c_name[PATH_MAX];
	const char *directory = NULL, *override;
	const char *base;
	int index = 1, result = 1, embedded_used = 0;

	if (index < argc && strcmp(argv[index], "--build-tree") == 0) {
		index++;
		directory = getenv("ET_DIR");
	}
	if (index >= argc || argv[index][0] == '\0') {
		puts("Usage: compile_et file");
		return 1;
	}
	override = getenv("_ET_DIR_OVERRIDE");
	if (override != NULL && *override != '\0')
		directory = override;
	if (directory == NULL) {
		if (embedded_templates(embedded, sizeof embedded, 1) != 0)
			goto done;
		directory = embedded;
		embedded_used = 1;
	}
	if (snprintf(h_template, sizeof h_template, "%s/et_h.awk", directory) >=
	    (int) sizeof h_template ||
	    snprintf(c_template, sizeof c_template, "%s/et_c.awk", directory) >=
	    (int) sizeof c_template || access(h_template, R_OK) != 0 ||
	    access(c_template, R_OK) != 0) {
		puts("compile_et: Couldn't find compile_et's template files.");
		goto done;
	}
	root = generator_root(argv[index], "et");
	if (root == NULL || (source = append_text(root, ".et")) == NULL)
		goto done;
	base = base_name(root);
	if (access(source, F_OK) != 0) {
		printf("compile_et: %s: File not found\n", source);
		goto done;
	}
	if (snprintf(h_temporary, sizeof h_temporary, "%s.h.%ld", base,
	    (long) getpid()) >= (int) sizeof h_temporary ||
	    snprintf(c_temporary, sizeof c_temporary, "%s.c.%ld", base,
	    (long) getpid()) >= (int) sizeof c_temporary ||
	    snprintf(h_name, sizeof h_name, "%s.h", base) >= (int) sizeof h_name ||
	    snprintf(c_name, sizeof c_name, "%s.c", base) >= (int) sizeof c_name ||
	    snprintf(h_variable, sizeof h_variable, "outfile=%s", h_temporary) >=
	    (int) sizeof h_variable ||
	    snprintf(c_variable, sizeof c_variable, "outfile=%s", c_temporary) >=
	    (int) sizeof c_variable)
		goto done;
	{
		char h_outfn[PATH_MAX + 16], c_outfn[PATH_MAX + 16];
		char *h_args[] = {"mawk", "-f", h_template, h_variable, h_outfn, source, NULL};
		char *c_args[] = {"mawk", "-f", c_template, c_variable, c_outfn, source, NULL};
		snprintf(h_outfn, sizeof h_outfn, "outfn=%s", h_name);
		snprintf(c_outfn, sizeof c_outfn, "outfn=%s", c_name);
		if (run_program(rustbox_gawk_main, "mawk", h_args, -1, -1) != 0 ||
		    publish_generated(h_temporary, h_name) != 0 ||
		    run_program(rustbox_gawk_main, "mawk", c_args, -1, -1) != 0 ||
		    publish_generated(c_temporary, c_name) != 0)
			goto done;
	}
	result = 0;
done:
	if (h_temporary[0] != '\0')
		unlink(h_temporary);
	if (c_temporary[0] != '\0')
		unlink(c_temporary);
	if (embedded_used)
		remove_templates(embedded, 1);
	free(root);
	free(source);
	return result;
}

static int
file_has_error_marker(const char *path)
{
	char line[4096];
	FILE *input = fopen(path, "r");
	if (input == NULL)
		return 1;
	while (fgets(line, sizeof line, input) != NULL)
		if (strncmp(line, "#__ERROR_IN_FILE", 16) == 0) {
			fclose(input);
			return 1;
		}
	fclose(input);
	return 0;
}

int
rustbox_e2fsprogs_mk_cmds_main(int argc, char **argv)
{
	char embedded[PATH_MAX] = "", sed_template[PATH_MAX], awk_template[PATH_MAX];
	char temporary[PATH_MAX] = "", output[PATH_MAX];
	char root_variable[PATH_MAX + 16], outfile_variable[PATH_MAX + 16];
	const char *directory = NULL, *override, *base;
	char *root = NULL;
	int pipes[2] = {-1, -1}, result = 1, embedded_used = 0;
	pid_t sed_child;

	if (argc < 2 || argv[1][0] == '\0') {
		puts("Usage: mk_cmds file");
		return 1;
	}
	override = getenv("_SS_DIR_OVERRIDE");
	if (override != NULL && *override != '\0')
		directory = override;
	if (directory == NULL) {
		if (embedded_templates(embedded, sizeof embedded, 0) != 0)
			goto done;
		directory = embedded;
		embedded_used = 1;
	}
	if (snprintf(sed_template, sizeof sed_template, "%s/ct_c.sed", directory) >=
	    (int) sizeof sed_template ||
	    snprintf(awk_template, sizeof awk_template, "%s/ct_c.awk", directory) >=
	    (int) sizeof awk_template || access(sed_template, R_OK) != 0 ||
	    access(awk_template, R_OK) != 0) {
		puts("mk_cmds: Couldn't find mk_cmds's template files.");
		goto done;
	}
	if (access(argv[1], F_OK) != 0) {
		printf("mk_cmds: %s: File not found\n", argv[1]);
		goto done;
	}
	root = generator_root(argv[1], "ct");
	if (root == NULL)
		goto done;
	base = base_name(root);
	if (snprintf(temporary, sizeof temporary, "ct%ld.c", (long) getpid()) >=
	    (int) sizeof temporary || snprintf(output, sizeof output, "%s.c", base) >=
	    (int) sizeof output || snprintf(root_variable, sizeof root_variable,
	    "rootname=%s", root) >= (int) sizeof root_variable ||
	    snprintf(outfile_variable, sizeof outfile_variable, "outfile=%s", temporary) >=
	    (int) sizeof outfile_variable || pipe(pipes) != 0)
		goto done;
	{
		char *sed_args[] = {"sed", "-f", sed_template, argv[1], NULL};
		char *awk_args[] = {"mawk", "-f", awk_template, root_variable,
		    outfile_variable, "-", NULL};
		sed_child = fork();
		if (sed_child == 0) {
			close(pipes[0]);
			if (pipes[1] != STDOUT_FILENO)
				dup2(pipes[1], STDOUT_FILENO);
			if (rustbox_sed_main != NULL) {
				int callback_status = rustbox_sed_main(4, sed_args);
				fflush(NULL);
				_exit(callback_status);
			}
			execvp("sed", sed_args);
			_exit(127);
		}
		close(pipes[1]);
		pipes[1] = -1;
		result = run_program(rustbox_gawk_main, "mawk", awk_args, pipes[0], -1);
		close(pipes[0]);
		pipes[0] = -1;
		wait_status(sed_child);
		if (result != 0 || file_has_error_marker(temporary)) {
			result = 1;
			goto done;
		}
	}
	unlink(output);
	if (rename(temporary, output) != 0)
		goto done;
	{
		struct stat status;
		if (stat(output, &status) != 0 ||
		    chmod(output, status.st_mode & ~(mode_t) 0222) != 0)
			goto done;
	}
	result = 0;
done:
	if (pipes[0] >= 0)
		close(pipes[0]);
	if (pipes[1] >= 0)
		close(pipes[1]);
	if (temporary[0] != '\0')
		unlink(temporary);
	if (embedded_used)
		remove_templates(embedded, 0);
	free(root);
	return result;
}

struct scrub_config {
	long snap_size_mb;
	int fstrim;
	int periodic_e2scrub;
	int scrub_all;
	char e2fsck_opts[512];
};

static void
read_scrub_config(struct scrub_config *config)
{
	char line[1024];
	FILE *input;
	config->snap_size_mb = 256;
	config->fstrim = 0;
	config->periodic_e2scrub = 0;
	config->scrub_all = 0;
	config->e2fsck_opts[0] = '\0';
	input = fopen("/etc/e2scrub.conf", "r");
	if (input == NULL)
		return;
	while (fgets(line, sizeof line, input) != NULL) {
		char *equals, *key, *value, *end;
		key = line;
		while (*key == ' ' || *key == '\t')
			key++;
		if (*key == '#' || *key == '\0')
			continue;
		equals = strchr(key, '=');
		if (equals == NULL)
			continue;
		*equals++ = '\0';
		end = key + strlen(key);
		while (end > key && (end[-1] == ' ' || end[-1] == '\t'))
			*--end = '\0';
		value = equals;
		while (*value == ' ' || *value == '\t')
			value++;
		value[strcspn(value, "\r\n#")] = '\0';
		end = value + strlen(value);
		while (end > value && (end[-1] == ' ' || end[-1] == '\t'))
			*--end = '\0';
		if (end - value >= 2 && ((*value == '"' && end[-1] == '"') ||
		    (*value == '\'' && end[-1] == '\''))) {
			value++;
			end[-1] = '\0';
		}
		if (strcmp(key, "snap_size_mb") == 0)
			config->snap_size_mb = strtol(value, NULL, 10);
		else if (strcmp(key, "fstrim") == 0)
			config->fstrim = atoi(value);
		else if (strcmp(key, "periodic_e2scrub") == 0)
			config->periodic_e2scrub = atoi(value);
		else if (strcmp(key, "scrub_all") == 0)
			config->scrub_all = atoi(value);
		else if (strcmp(key, "e2fsck_opts") == 0)
			snprintf(config->e2fsck_opts, sizeof config->e2fsck_opts,
			    "%s", value);
	}
	fclose(input);
}

static int
capture_program(applet_main callback, const char *external, char **arguments,
    int suppress_stderr, char **captured)
{
	int pipe_fd[2], null_fd = -1, status;
	pid_t child;
	size_t used = 0, capacity = 4096;
	char *output;
	*captured = NULL;
	output = malloc(capacity);
	if (output == NULL || pipe(pipe_fd) != 0) {
		free(output);
		return 127;
	}
	fflush(NULL);
	child = fork();
	if (child == 0) {
		int count = 0, callback_status;
		close(pipe_fd[0]);
		dup2(pipe_fd[1], STDOUT_FILENO);
		close(pipe_fd[1]);
		if (suppress_stderr) {
			null_fd = open("/dev/null", O_WRONLY);
			if (null_fd >= 0)
				dup2(null_fd, STDERR_FILENO);
		}
		while (arguments[count] != NULL)
			count++;
		setenv("LC_ALL", "C", 1);
		setenv("LANG", "C", 1);
		setenv("PATH", "/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin", 1);
		if (callback != NULL) {
			callback_status = callback(count, arguments);
			fflush(NULL);
			_exit(callback_status);
		}
		execvp(external, arguments);
		_exit(127);
	}
	close(pipe_fd[1]);
	for (;;) {
		ssize_t count;
		if (used == capacity) {
			char *larger;
			capacity *= 2;
			larger = realloc(output, capacity);
			if (larger == NULL) {
				free(output);
				close(pipe_fd[0]);
				wait_status(child);
				return 127;
			}
			output = larger;
		}
		count = read(pipe_fd[0], output + used, capacity - used);
		if (count > 0) {
			used += (size_t) count;
			continue;
		}
		if (count < 0 && errno == EINTR)
			continue;
		break;
	}
	close(pipe_fd[0]);
	if (used == capacity) {
		char *larger = realloc(output, capacity + 1);
		if (larger == NULL) {
			free(output);
			wait_status(child);
			return 127;
		}
		output = larger;
	}
	output[used] = '\0';
	status = wait_status(child);
	*captured = output;
	return status;
}

static void
trim_text(char *text)
{
	char *start = text, *end;
	while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n')
		start++;
	if (start != text)
		memmove(text, start, strlen(start) + 1);
	end = text + strlen(text);
	while (end > text && (end[-1] == ' ' || end[-1] == '\t' ||
	    end[-1] == '\r' || end[-1] == '\n'))
		*--end = '\0';
}

static char *
quoted_value(const char *line, const char *key)
{
	char pattern[64];
	const char *start, *end, *search = line;
	char *value;
	snprintf(pattern, sizeof pattern, "%s=\"", key);
	for (;;) {
		start = strstr(search, pattern);
		if (start == NULL)
			return NULL;
		if (start == line || start[-1] == ' ' || start[-1] == '\t')
			break;
		search = start + 1;
	}
	start += strlen(pattern);
	end = strchr(start, '"');
	if (end == NULL)
		return NULL;
	value = malloc((size_t) (end - start) + 1);
	if (value == NULL)
		return NULL;
	memcpy(value, start, (size_t) (end - start));
	value[end - start] = '\0';
	return value;
}

static char *
lvm_assignment(const char *text, const char *key)
{
	char pattern[64];
	const char *start, *end;
	char quote = '\0', *value;
	snprintf(pattern, sizeof pattern, "%s=", key);
	start = strstr(text, pattern);
	if (start == NULL)
		return NULL;
	start += strlen(pattern);
	while (*start == ' ' || *start == '\t')
		start++;
	if (*start == '\'' || *start == '"')
		quote = *start++;
	end = start;
	while (*end != '\0' && (quote ? *end != quote :
	    *end != ' ' && *end != '\t' && *end != '\r' && *end != '\n'))
		end++;
	value = malloc((size_t) (end - start) + 1);
	if (value == NULL)
		return NULL;
	memcpy(value, start, (size_t) (end - start));
	value[end - start] = '\0';
	return value;
}

static int
split_words(const char *text, char **output, int capacity)
{
	int count = 0;
	char *copy = strdup(text), *cursor, *token;
	if (copy == NULL)
		return 0;
	cursor = copy;
	while (count < capacity - 1 && (token = strsep(&cursor, " \t\r\n")) != NULL)
		if (*token != '\0')
			output[count++] = strdup(token);
	free(copy);
	output[count] = NULL;
	return count;
}

static void
free_words(char **words, int count)
{
	while (count > 0)
		free(words[--count]);
}

static int
run_external(char **arguments, int suppress_stderr)
{
	pid_t child;
	fflush(NULL);
	child = fork();
	if (child == 0) {
		if (suppress_stderr) {
			int null_fd = open("/dev/null", O_WRONLY);
			if (null_fd >= 0)
				dup2(null_fd, STDERR_FILENO);
		}
		setenv("PATH", "/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin", 1);
		execvp(arguments[0], arguments);
		_exit(127);
	}
	return wait_status(child);
}

static int
run_applet_or_external(applet_main callback, char **arguments, int suppress_stderr)
{
	if (callback == NULL)
		return run_external(arguments, suppress_stderr);
	return run_program(callback, arguments[0], arguments, -1, -1);
}

static void
print_dry_command(char **arguments)
{
	int index;
	fputs("Would execute: ", stdout);
	for (index = 0; arguments[index] != NULL; index++) {
		if (index != 0)
			putchar(' ');
		fputs(arguments[index], stdout);
	}
	putchar('\n');
}

static void
e2scrub_help(const char *program)
{
	printf("Usage: %s [OPTIONS] mountpoint | device\n\n", program);
	puts("mountpoint must be on an LVM-managed block device");
	puts("-n: Show what commands e2scrub would execute.");
	puts("-r: Remove e2scrub snapshot and exit, do not check anything.");
	puts("-t: Run fstrim if successful.");
	puts("-V: Print version information and exit.");
}

static void
e2scrub_all_help(const char *program)
{
	printf("Usage: %s [OPTIONS]\n", program);
	puts(" -n: Show what commands e2scrub_all would execute.");
	puts(" -r: Remove e2scrub snapshots.");
	puts(" -A: Scrub all ext[234] filesystems even if not mounted.");
	puts(" -V: Print version information and exit.");
}

static int
fixed_command_exists(const char *name)
{
	static const char *const directories[] = {
		"/usr/local/sbin", "/usr/local/bin", "/sbin", "/bin",
		"/usr/sbin", "/usr/bin",
	};
	char path[PATH_MAX];
	size_t index;
	for (index = 0; index < sizeof directories / sizeof directories[0]; index++) {
		snprintf(path, sizeof path, "%s/%s", directories[index], name);
		if (access(path, X_OK) == 0)
			return 1;
	}
	return 0;
}

static int
parse_scrub_options(int argc, char **argv, const char *accepted, int *index,
    int *version, int *flags, void (*help)(const char *))
{
	for (*index = 1; *index < argc; (*index)++) {
		const char *option = argv[*index];
		int offset;
		if (option[0] != '-' || option[1] == '\0')
			break;
		if (strcmp(option, "--") == 0) {
			(*index)++;
			break;
		}
		for (offset = 1; option[offset] != '\0'; offset++) {
			char value = option[offset];
			if (strchr(accepted, value) == NULL) {
				fprintf(stderr, "%s: illegal option -- %c\n", argv[0], value);
				help(argv[0]);
				return 2;
			}
			if (value == 'V')
				*version = 1;
			else if (value == 'n')
				*flags |= SCRUB_DRY_RUN;
			else if (value == 'r')
				*flags |= SCRUB_REAP;
			else if (value == 't')
				*flags |= SCRUB_TRIM;
			else if (value == 'A')
				*flags |= SCRUB_ALL;
		}
	}
	return 0;
}

struct scrub_target {
	char *device;
	char *mountpoint;
	char *vg;
	char *lv;
	char *snapshot;
	char *snapshot_device;
};

static void
free_scrub_target(struct scrub_target *target)
{
	free(target->device);
	free(target->mountpoint);
	free(target->vg);
	free(target->lv);
	free(target->snapshot);
	free(target->snapshot_device);
	memset(target, 0, sizeof *target);
}

static int
is_ext_filesystem(const char *value)
{
	return strcmp(value, "ext2") == 0 || strcmp(value, "ext3") == 0 ||
	    strcmp(value, "ext4") == 0;
}

static int
resolve_scrub_target(const char *argument, struct scrub_target *target)
{
	struct stat status;
	char *output = NULL;
	int command_status;
	if (stat(argument, &status) == 0 && S_ISBLK(status.st_mode)) {
		char *fstype_args[] = {"lsblk", "-o", "FSTYPE", "-n",
		    (char *) argument, NULL};
		char *mount_args[] = {"lsblk", "-o", "MOUNTPOINT", "-n",
		    (char *) argument, NULL};
		command_status = capture_program(rustbox_lsblk_main, "lsblk",
		    fstype_args, 1, &output);
		if (command_status != 0)
			goto failed;
		trim_text(output);
		if (!is_ext_filesystem(output))
			goto failed;
		free(output);
		output = NULL;
		target->device = strdup(argument);
		command_status = capture_program(rustbox_lsblk_main, "lsblk",
		    mount_args, 0, &output);
		if (command_status != 0)
			goto failed;
		trim_text(output);
		target->mountpoint = strdup(output);
		free(output);
		return target->device != NULL && target->mountpoint != NULL ? 0 : -1;
	} else {
		char resolved[PATH_MAX];
		char *scan_args[] = {"lsblk", "-o", "NAME,FSTYPE,MOUNTPOINT", "-p",
		    "-P", "-n", NULL};
		char *line, *save;
		if (realpath(argument, resolved) == NULL)
			resolved[0] = '\0';
		command_status = capture_program(rustbox_lsblk_main, "lsblk",
		    scan_args, 1, &output);
		if (command_status != 0)
			goto failed;
		for (line = strtok_r(output, "\n", &save); line != NULL;
		    line = strtok_r(NULL, "\n", &save)) {
			char *name = quoted_value(line, "NAME");
			char *fstype = quoted_value(line, "FSTYPE");
			char *mountpoint = quoted_value(line, "MOUNTPOINT");
			if (name != NULL && fstype != NULL && mountpoint != NULL &&
			    strcmp(mountpoint, resolved) == 0 && is_ext_filesystem(fstype)) {
				target->device = name;
				target->mountpoint = strdup(argument);
				free(fstype);
				free(mountpoint);
				free(output);
				return target->mountpoint == NULL ? -1 : 0;
			}
			free(name);
			free(fstype);
			free(mountpoint);
		}
	}
failed:
	free(output);
	return -1;
}

static int
target_has_journal(const char *device)
{
	char *output = NULL;
	char *arguments[] = {"dumpe2fs", "-h", (char *) device, NULL};
	int status = capture_program(rustbox_e2fsprogs_dumpe2fs_main, "dumpe2fs",
	    arguments, 0, &output);
	int journal = status == 0 && output != NULL &&
	    strstr(output, "has_journal") != NULL;
	free(output);
	return journal;
}

static int
load_lvm_identity(struct scrub_target *target)
{
	char *output = NULL;
	char *arguments[] = {"lvs", "--nameprefixes", "-o", "name,vgname,lv_role",
	    "--noheadings", target->device, NULL};
	if (capture_program(NULL, "lvs", arguments, 1, &output) != 0) {
		free(output);
		return -1;
	}
	target->vg = lvm_assignment(output, "LVM2_VG_NAME");
	target->lv = lvm_assignment(output, "LVM2_LV_NAME");
	{
		char *role = lvm_assignment(output, "LVM2_LV_ROLE");
		int invalid = target->vg == NULL || *target->vg == '\0' ||
		    target->lv == NULL || *target->lv == '\0' ||
		    (role != NULL && strstr(role, "snapshot") != NULL);
		free(role);
		free(output);
		if (invalid)
			return -1;
	}
	if (asprintf(&target->snapshot, "%s.e2scrub", target->lv) < 0 ||
	    asprintf(&target->snapshot_device, "/dev/%s/%s", target->vg,
	    target->snapshot) < 0)
		return -1;
	return 0;
}

static int
run_or_print(applet_main callback, char **arguments, int dry_run,
    int suppress_stderr)
{
	if (dry_run) {
		print_dry_command(arguments);
		return 0;
	}
	return run_applet_or_external(callback, arguments, suppress_stderr);
}

static int
remove_snapshot(struct scrub_target *target, int dry_run, int suppress_stderr)
{
	char identity[PATH_MAX];
	char *arguments[] = {"lvremove", "-f", identity, NULL};
	int status, attempts = 0;
	snprintf(identity, sizeof identity, "%s/%s", target->vg, target->snapshot);
	do {
		status = run_or_print(NULL, arguments, dry_run, suppress_stderr);
		if (dry_run || status != 5 || access(target->snapshot_device, F_OK) != 0)
			break;
		usleep(500000);
	} while (++attempts < 60);
	return status;
}

static int
run_e2fsck_check(struct scrub_target *target, const struct scrub_config *config,
    int dry_run)
{
	char *extra[64] = {NULL};
	char *first[72], *second[72];
	const char *old_fixes_value = getenv("E2FSCK_FIXES_ONLY");
	char *old_fixes = old_fixes_value == NULL ? NULL : strdup(old_fixes_value);
	if (old_fixes_value != NULL && old_fixes == NULL)
		return 127;
	int extra_count = split_words(config->e2fsck_opts, extra, 64);
	int index = 0, status;
	first[index++] = "/sbin/e2fsck";
	first[index++] = "-E";
	first[index++] = "journal_only";
	first[index++] = "-p";
	for (int item = 0; item < extra_count; item++)
		first[index++] = extra[item];
	first[index++] = target->snapshot_device;
	first[index] = NULL;
	setenv("E2FSCK_FIXES_ONLY", "1", 1);
	status = run_or_print(rustbox_e2fsprogs_e2fsck_main, first, dry_run, 0);
	if (status == 0) {
		index = 0;
		second[index++] = "/sbin/e2fsck";
		second[index++] = "-f";
		second[index++] = "-y";
		for (int item = 0; item < extra_count; item++)
			second[index++] = extra[item];
		second[index++] = target->snapshot_device;
		second[index] = NULL;
		status = run_or_print(rustbox_e2fsprogs_e2fsck_main, second, dry_run, 0);
	}
	free_words(extra, extra_count);
	if (old_fixes != NULL) {
		setenv("E2FSCK_FIXES_ONLY", old_fixes, 1);
		free(old_fixes);
	} else
		unsetenv("E2FSCK_FIXES_ONLY");
	return status;
}

static int
snapshot_is_invalid(const char *snapshot_device)
{
	char *output = NULL;
	char *arguments[] = {"lvs", "-o", "lv_snapshot_invalid", "--noheadings",
	    (char *) snapshot_device, NULL};
	if (capture_program(NULL, "lvs", arguments, 0, &output) != 0 ||
	    output == NULL) {
		free(output);
		return 0;
	}
	trim_text(output);
	{
		int invalid = output[0] != '\0';
		free(output);
		return invalid;
	}
}

static int
add_string(char ***items, size_t *count, const char *value)
{
	char **larger = realloc(*items, (*count + 1) * sizeof **items);
	if (larger == NULL)
		return -1;
	*items = larger;
	(*items)[*count] = strdup(value);
	if ((*items)[*count] == NULL)
		return -1;
	(*count)++;
	return 0;
}

static void
free_strings(char **items, size_t count)
{
	while (count > 0)
		free(items[--count]);
	free(items);
}

static int
collect_reap_targets(char ***targets, size_t *target_count)
{
	char *output = NULL, *line, *save;
	char *arguments[] = {"lvs", "-o", "lv_path", "-S", "lv_role=snapshot",
	    "-S", "lv_name=~(e2scrub$)", "--noheadings", NULL};
	if (capture_program(NULL, "lvs", arguments, 0, &output) != 0) {
		free(output);
		return -1;
	}
	for (line = strtok_r(output, "\n", &save); line != NULL;
	    line = strtok_r(NULL, "\n", &save)) {
		size_t length;
		trim_text(line);
		length = strlen(line);
		if (length >= 8 && strcmp(line + length - 8, ".e2scrub") == 0)
			line[length - 8] = '\0';
		if (*line != '\0' && add_string(targets, target_count, line) != 0) {
			free(output);
			return -1;
		}
	}
	free(output);
	return 0;
}

static int
collect_scan_targets(const struct scrub_config *config, int scrub_all,
    char ***targets, size_t *target_count)
{
	char selection[256], *lvs_output = NULL, *lsblk_output = NULL;
	char *devices[256] = {NULL}, *word, *cursor, *copy;
	char *lvs_arguments[] = {"lvs", "-o", "lv_path", "--noheadings", "-S",
	    selection, NULL};
	char *lsblk_arguments[270];
	int device_count = 0, argument_count = 0;
	snprintf(selection, sizeof selection,
	    "lv_active=active,lv_role=public,lv_role!=snapshot,vg_free>=%ld",
	    config->snap_size_mb);
	if (capture_program(NULL, "lvs", lvs_arguments, 0, &lvs_output) != 0)
		goto failed;
	copy = strdup(lvs_output);
	if (copy == NULL)
		goto failed;
	cursor = copy;
	while (device_count < 255 && (word = strsep(&cursor, " \t\r\n")) != NULL)
		if (*word != '\0')
			devices[device_count++] = strdup(word);
	free(copy);
	if (device_count == 0) {
		free(lvs_output);
		return 0;
	}
	lsblk_arguments[argument_count++] = "lsblk";
	lsblk_arguments[argument_count++] = "-o";
	lsblk_arguments[argument_count++] = "NAME,MOUNTPOINT,FSTYPE,TYPE";
	lsblk_arguments[argument_count++] = "-P";
	lsblk_arguments[argument_count++] = "-n";
	lsblk_arguments[argument_count++] = "-p";
	for (int index = 0; index < device_count; index++)
		lsblk_arguments[argument_count++] = devices[index];
	lsblk_arguments[argument_count] = NULL;
	if (capture_program(rustbox_lsblk_main, "lsblk", lsblk_arguments, 0,
	    &lsblk_output) != 0)
		goto failed;
	{
		char *line, *save;
		for (line = strtok_r(lsblk_output, "\n", &save); line != NULL;
		    line = strtok_r(NULL, "\n", &save)) {
			char *name = quoted_value(line, "NAME");
			char *mountpoint = quoted_value(line, "MOUNTPOINT");
			char *fstype = quoted_value(line, "FSTYPE");
			char *type = quoted_value(line, "TYPE");
			if (name != NULL && mountpoint != NULL && fstype != NULL && type != NULL &&
			    is_ext_filesystem(fstype) && strcmp(type, "lvm") == 0 &&
			    target_has_journal(name) && (scrub_all || *mountpoint != '\0'))
				add_string(targets, target_count,
				    *mountpoint != '\0' ? mountpoint : name);
			free(name);
			free(mountpoint);
			free(fstype);
			free(type);
		}
	}
	for (int index = 0; index < device_count; index++)
		free(devices[index]);
	free(lvs_output);
	free(lsblk_output);
	return 0;
failed:
	for (int index = 0; index < device_count; index++)
		free(devices[index]);
	free(lvs_output);
	free(lsblk_output);
	return -1;
}

int
rustbox_e2fsprogs_e2scrub_main(int argc, char **argv)
{
	struct scrub_config config;
	struct scrub_target target = {0};
	int index, version = 0, flags = 0, status, result = 8;
	char size[64], identity[PATH_MAX], start_time[32];
	time_t now;
	if (geteuid() != 0) {
		puts("e2scrub must be run as root");
		return 1;
	}
	read_scrub_config(&config);
	status = parse_scrub_options(argc, argv, "nrtV", &index, &version,
	    &flags, e2scrub_help);
	if (status != 0)
		return status;
	if (version) {
		printf("e2scrub %s (%s)\n", E2FSPROGS_VERSION, E2FSPROGS_DATE);
		return 0;
	}
	if (index >= argc || argv[index][0] == '\0') {
		e2scrub_help(argv[0]);
		return 1;
	}
	if (!fixed_command_exists("lsblk")) {
		puts("e2scrub: can't find lsblk --- is util-linux installed?");
		return 1;
	}
	if (!fixed_command_exists("lvcreate")) {
		puts("e2scrub: can't find lvcreate --- is lvm2 installed?");
		return 1;
	}
	close(3);
	if (resolve_scrub_target(argv[index], &target) != 0 || target.device == NULL ||
	    access(target.device, F_OK) != 0) {
		printf("%s: Not an ext[234] filesystem.\n", argv[index]);
		e2scrub_help(argv[0]);
		result = 16;
		goto done;
	}
	if (!(flags & SCRUB_REAP) && !target_has_journal(target.device)) {
		printf("%s: Filesystem has no journal, cannot check.\n", argv[index]);
		e2scrub_help(argv[0]);
		result = 16;
		goto done;
	}
	if (load_lvm_identity(&target) != 0) {
		printf("%s: Not connected to an LVM logical volume.\n", argv[index]);
		e2scrub_help(argv[0]);
		result = 16;
		goto done;
	}
	now = time(NULL);
	strftime(start_time, sizeof start_time, "%Y%m%d%H%M%S", localtime(&now));
	if (flags & SCRUB_REAP) {
		if (access(target.snapshot_device, F_OK) == 0)
			remove_snapshot(&target, flags & SCRUB_DRY_RUN, 1);
		result = 0;
		goto done;
	}

	/* Remove stale snapshots before creating a new one. */
	remove_snapshot(&target, flags & SCRUB_DRY_RUN, 1);
	if (!(flags & SCRUB_DRY_RUN) && access(target.snapshot_device, F_OK) == 0) {
		printf("%s: e2scrub snapshot is in use, cannot check!\n", argv[index]);
		result = 8;
		goto done;
	}
	snprintf(size, sizeof size, "%ldm", config.snap_size_mb);
	snprintf(identity, sizeof identity, "%s/%s", target.vg, target.lv);
	{
		char *arguments[] = {"lvcreate", "-s", "-L", size, "-n",
		    target.snapshot, identity, NULL};
		status = run_or_print(NULL, arguments, flags & SCRUB_DRY_RUN, 0);
	}
	if (status != 0) {
		printf("%s: e2scrub snapshot FAILED, will not check!\n", argv[index]);
		result = 8;
		goto done;
	}
	{
		char *arguments[] = {"udevadm", "settle", NULL};
		run_or_print(NULL, arguments, flags & SCRUB_DRY_RUN, 1);
	}
	status = run_e2fsck_check(&target, &config, flags & SCRUB_DRY_RUN);
	if (status == 0) {
		char *mark_arguments[] = {"/sbin/tune2fs", "-C", "0", "-T",
		    start_time, target.device, NULL};
		printf("%s: Scrub succeeded.\n", argv[index]);
		run_or_print(rustbox_e2fsprogs_tune2fs_main, mark_arguments,
		    flags & SCRUB_DRY_RUN, 0);
		remove_snapshot(&target, flags & SCRUB_DRY_RUN, 0);
		if (((flags & SCRUB_TRIM) || config.fstrim == 1) &&
		    target.mountpoint != NULL && *target.mountpoint != '\0') {
			struct stat mount_status;
			if (stat(target.mountpoint, &mount_status) == 0 &&
			    S_ISDIR(mount_status.st_mode) && fixed_command_exists("fstrim")) {
				char *trim_arguments[] = {"fstrim", "-v", target.mountpoint, NULL};
				printf("%s: Trimming free space.\n", argv[index]);
				run_or_print(NULL, trim_arguments, flags & SCRUB_DRY_RUN, 0);
			}
		}
		result = 0;
	} else if (status == 8) {
		printf("%s: e2fsck operational error.\n", argv[index]);
		remove_snapshot(&target, flags & SCRUB_DRY_RUN, 0);
		result = 8;
	} else {
		if (snapshot_is_invalid(target.snapshot_device)) {
			printf("%s: Scrub FAILED due to invalid snapshot.\n", argv[index]);
			result = 8;
		} else {
			char *mark_arguments[] = {"/sbin/tune2fs", "-E", "force_fsck",
			    target.device, NULL};
			printf("%s: Scrub FAILED due to corruption!  Unmount and run e2fsck -y.\n",
			    argv[index]);
			run_or_print(rustbox_e2fsprogs_tune2fs_main, mark_arguments,
			    flags & SCRUB_DRY_RUN, 0);
			result = 6;
		}
		remove_snapshot(&target, flags & SCRUB_DRY_RUN, 0);
	}
done:
	free_scrub_target(&target);
	if (getenv("SERVICE_MODE") != NULL && result != 0) {
		sleep(2);
		return 1;
	}
	return result;
}

int
rustbox_e2fsprogs_e2scrub_all_main(int argc, char **argv)
{
	struct scrub_config config;
	char **targets = NULL;
	size_t target_count = 0, target_index;
	int index, version = 0, flags = 0, status;
	if (geteuid() != 0) {
		puts("e2scrub_all must be run as root");
		return 1;
	}
	read_scrub_config(&config);
	status = parse_scrub_options(argc, argv, "nrAV", &index, &version,
	    &flags, e2scrub_all_help);
	if (status != 0)
		return status;
	if (version) {
		printf("e2scrub_all %s (%s)\n", E2FSPROGS_VERSION, E2FSPROGS_DATE);
		return 0;
	}
	if (getenv("SERVICE_MODE") != NULL && config.periodic_e2scrub != 1) {
		if (!(flags & SCRUB_REAP))
			return 0;
		else {
			glob_t matches;
			int found = glob("/dev/mapper/*.e2scrub*", 0, NULL, &matches) == 0;
			globfree(&matches);
			if (!found)
				return 0;
		}
	}
	if (!fixed_command_exists("lsblk")) {
		puts("e2scrub_all: can't find lsblk --- is util-linux installed?");
		return getenv("SERVICE_MODE") == NULL ? 1 : 0;
	}
	if (!fixed_command_exists("lvcreate")) {
		puts("e2scrub_all: can't find lvcreate --- is lvm2 installed?");
		return getenv("SERVICE_MODE") == NULL ? 1 : 0;
	}
	close(3);
	if (flags & SCRUB_REAP)
		collect_reap_targets(&targets, &target_count);
	else
		collect_scan_targets(&config,
		    (flags & SCRUB_ALL) || config.scrub_all == 1,
		    &targets, &target_count);
	for (target_index = 0; target_index < target_count; target_index++) {
		char *arguments[4];
		int argument_count = 0;
		arguments[argument_count++] = "/sbin/e2scrub";
		if (flags & SCRUB_REAP)
			arguments[argument_count++] = "-r";
		arguments[argument_count++] = targets[target_index];
		arguments[argument_count] = NULL;
		if (flags & SCRUB_DRY_RUN)
			print_dry_command(arguments);
		else
			run_program(rustbox_e2fsprogs_e2scrub_main, "/sbin/e2scrub",
			    arguments, -1, -1);
	}
	free_strings(targets, target_count);
	return 0;
}

#ifndef RUSTBOX_MULTICALL
int
main(int argc, char **argv)
{
	const char *name = base_name(argv[0]);
	if (strcmp(name, "compile_et") == 0)
		return rustbox_e2fsprogs_compile_et_main(argc, argv);
	if (strcmp(name, "mk_cmds") == 0)
		return rustbox_e2fsprogs_mk_cmds_main(argc, argv);
	if (strcmp(name, "e2scrub") == 0)
		return rustbox_e2fsprogs_e2scrub_main(argc, argv);
	if (strcmp(name, "e2scrub_all") == 0)
		return rustbox_e2fsprogs_e2scrub_all_main(argc, argv);
	fprintf(stderr, "unknown E2fsprogs script frontend: %s\n", name);
	return 127;
}
#endif
