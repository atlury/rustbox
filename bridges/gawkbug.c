/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Native replacement for GNU Gawk's generated gawkbug shell frontend. */

#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pwd.h>
#include <signal.h>
#include <spawn.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

#define GAWKBUG_VERSION "5.4.0"
#define INITIAL_SUBJECT "[50 character or so descriptive subject here (for reference)]"

static char temporary_directory[PATH_MAX];
static char temporary_report[PATH_MAX];
static char temporary_original[PATH_MAX];
extern char **environ;

static void
remove_temporary_directory(void)
{
	if (temporary_directory[0] == '\0')
		return;
	unlink(temporary_report);
	unlink(temporary_original);
	rmdir(temporary_directory);
	temporary_directory[0] = '\0';
}

static void
handle_signal(int signal_number)
{
	remove_temporary_directory();
	_exit(128 + signal_number);
}

static int
copy_file(const char *source, const char *destination)
{
	char buffer[16384];
	ssize_t count;
	int input = open(source, O_RDONLY);
	int output;

	if (input < 0)
		return -1;
	output = open(destination, O_WRONLY | O_CREAT | O_TRUNC, 0600);
	if (output < 0) {
		close(input);
		return -1;
	}
	while ((count = read(input, buffer, sizeof buffer)) > 0) {
		ssize_t offset = 0;
		while (offset < count) {
			ssize_t written = write(output, buffer + offset,
			    (size_t) (count - offset));
			if (written < 0) {
				close(input);
				close(output);
				return -1;
			}
			offset += written;
		}
	}
	{
		int failed = count < 0;
		if (close(input) != 0)
			failed = 1;
		if (close(output) != 0)
			failed = 1;
		return failed ? -1 : 0;
	}
}

static int
files_equal(const char *left, const char *right)
{
	char left_buffer[8192], right_buffer[8192];
	ssize_t left_count, right_count;
	int left_fd = open(left, O_RDONLY);
	int right_fd = open(right, O_RDONLY);
	int equal = 1;

	if (left_fd < 0 || right_fd < 0) {
		if (left_fd >= 0)
			close(left_fd);
		if (right_fd >= 0)
			close(right_fd);
		return 0;
	}
	do {
		left_count = read(left_fd, left_buffer, sizeof left_buffer);
		right_count = read(right_fd, right_buffer, sizeof right_buffer);
		if (left_count != right_count || left_count < 0 ||
		    (left_count > 0 && memcmp(left_buffer, right_buffer,
		    (size_t) left_count) != 0)) {
			equal = 0;
			break;
		}
	} while (left_count > 0);
	close(left_fd);
	close(right_fd);
	return equal;
}

static char *
shell_quote(const char *value)
{
	size_t length = 3;
	const char *cursor;
	char *result, *output;

	for (cursor = value; *cursor; cursor++)
		length += *cursor == '\'' ? 4 : 1;
	result = malloc(length);
	if (result == NULL)
		return NULL;
	output = result;
	*output++ = '\'';
	for (cursor = value; *cursor; cursor++) {
		if (*cursor == '\'') {
			memcpy(output, "'\\''", 4);
			output += 4;
		} else
			*output++ = *cursor;
	}
	*output++ = '\'';
	*output = '\0';
	return result;
}

static int
run_editor(const char *editor, const char *path)
{
	char *quoted = shell_quote(path);
	char *command;
	pid_t child;
	int status;

	if (quoted == NULL)
		return 127;
	if (asprintf(&command, "%s %s", editor, quoted) < 0) {
		free(quoted);
		return 127;
	}
	free(quoted);
	child = fork();
	if (child == 0) {
		execl("/bin/sh", "sh", "-c", command, (char *) NULL);
		_exit(127);
	}
	free(command);
	if (child < 0 || waitpid(child, &status, 0) < 0)
		return 127;
	return WIFEXITED(status) ? WEXITSTATUS(status) : 128;
}

static int
run_mailer(const char *mailer, int sendmail, const char *address,
    const char *report)
{
	posix_spawn_file_actions_t actions;
	char *sendmail_arguments[] = {(char *) mailer, "-i", "-t", NULL};
	char *rmail_arguments[] = {(char *) mailer, (char *) address, NULL};
	pid_t child;
	int input = open(report, O_RDONLY);
	int status;
	int error;

	if (input < 0 || posix_spawn_file_actions_init(&actions) != 0) {
		if (input >= 0)
			close(input);
		return 127;
	}
	if (input != STDIN_FILENO &&
	    (posix_spawn_file_actions_adddup2(&actions, input, STDIN_FILENO) != 0 ||
	    posix_spawn_file_actions_addclose(&actions, input) != 0)) {
		posix_spawn_file_actions_destroy(&actions);
		close(input);
		return 127;
	}
	if (sendmail)
		error = posix_spawn(&child, mailer, &actions, NULL,
		    sendmail_arguments, environ);
	else
		error = posix_spawnp(&child, mailer, &actions, NULL,
		    rmail_arguments, environ);
	posix_spawn_file_actions_destroy(&actions);
	close(input);
	if (error != 0 || waitpid(child, &status, 0) < 0)
		return 127;
	return WIFEXITED(status) ? WEXITSTATUS(status) : 128;
}

static int
read_answer(void)
{
	char answer[64];
	if (fgets(answer, sizeof answer, stdin) == NULL)
		return '\0';
	return answer[0];
}

static int
subject_is_default(const char *path)
{
	char line[4096];
	FILE *input = fopen(path, "r");

	if (input == NULL)
		return 0;
	while (fgets(line, sizeof line, input) != NULL) {
		char *subject;
		if (strncmp(line, "Subject:", 8) != 0)
			continue;
		subject = line + 8;
		while (*subject == ' ' || *subject == '\t')
			subject++;
		subject[strcspn(subject, "\r\n")] = '\0';
		fclose(input);
		return strcmp(subject, INITIAL_SUBJECT) == 0;
	}
	fclose(input);
	return 0;
}

static const char *
select_editor(void)
{
	static const char *const candidates[] = {
		"/usr/bin/editor", "/usr/bin/vim", "/usr/bin/gvim",
		"/usr/local/bin/ce", "/usr/local/bin/emacs",
		"/usr/contrib/bin/emacs", "/usr/bin/emacs", "/usr/bin/xemacs",
		"/usr/bin/nano", "/usr/contrib/bin/jove", "/usr/local/bin/jove",
		"/usr/bin/vi",
	};
	const char *editor = getenv("EDITOR");
	const char *fallback = getenv("DEFEDITOR");
	size_t index;

	if (editor != NULL && *editor != '\0')
		return editor;
	if (fallback != NULL && *fallback != '\0')
		return fallback;
	for (index = 0; index < sizeof candidates / sizeof candidates[0]; index++)
		if (access(candidates[index], X_OK) == 0)
			return candidates[index];
	fprintf(stderr, "gawkbug: No default editor found: attempting to use vi\n");
	return "vi";
}

static const char *
current_user(void)
{
	const char *user = getenv("USER");
	struct passwd *entry;

	if (user != NULL && *user != '\0')
		return user;
	user = getenv("LOGNAME");
	if (user != NULL && *user != '\0')
		return user;
	entry = getpwuid(getuid());
	return entry != NULL ? entry->pw_name : "unknown";
}

static void
print_help(const char *program)
{
	printf("GNU gawkbug, version %s\n", GAWKBUG_VERSION);
	printf("Usage: %s [--help] [--version] [bug-report-email-address]\n\n",
	    program);
	fputs(
	    "Gawkbug is used to send mail to the Gawk maintainers\n"
	    "for when Gawk doesn't behave like you'd like, or expect.\n\n"
	    "Gawkbug will start up your editor (as defined by the shell's\n"
	    "EDITOR environment variable) with a preformatted bug report\n"
	    "template for you to fill in. The report will be mailed to the\n"
	    "bug-gawk mailing list by default.\n\n"
	    "Please see https://www.gnu.org/software/gawk/manual/html_node/Bugs.html\n"
	    "for bug reporting instructions.  Reading that information before\n"
	    "repoting a bug will make everyones' lives easier.\n\n"
	    "If you invoke gawkbug by accident, just quit your editor without\n"
	    "saving any changes to the template, and no bug report will be sent.\n",
	    stdout);
}

static int
write_template(const char *path, const char *user, const char *address,
    const char *uname_output)
{
	FILE *output = fopen(path, "w");

	if (output == NULL)
		return -1;
	fprintf(output,
	    "From: %s\n"
	    "To: %s\n"
	    "Subject: %s\n\n"
	    "Configuration Information [Automatically generated, do not change]:\n"
	    "Machine: x86_64\n"
	    "OS: linux-gnu\n"
	    "Compiler: clang-18\n"
	    "Compilation CFLAGS: -O2 -g -fno-omit-frame-pointer\n"
	    "uname output: %s\n"
	    "Machine Type: x86_64-pc-linux-gnu\n\n"
	    "Gawk Version: %s\n\n"
	    "Attestation 1:\n"
	    "\tI have read https://www.gnu.org/software/gawk/manual/html_node/Bugs.html.\n"
	    "\tYes / No  [ Choose one. If \"No\", then why haven't you? ]\n\n"
	    "Attestation 2:\n"
	    "\tI have not modified the sources before building gawk.\n"
	    "\tTrue / False\n"
	    "\t[ Choose one. If \"False\", then please explain what you did and why. ]\n\n"
	    "Description:\n"
	    "\t[Detailed description of the problem, suggestion, or complaint.]\n\n"
	    "Repeat-By:\n"
	    "\t[Describe the sequence of events that causes the problem to occur.]\n\n"
	    "Fix:\n"
	    "\t[Description of how to fix the problem.  If you don't know a\n"
	    "\tfix for the problem, don't include this section.]\n",
	    user, address, INITIAL_SUBJECT, uname_output, GAWKBUG_VERSION);
	return fclose(output);
}

int
rustbox_gawkbug_main(int argc, char **argv)
{
	const char *program = argv[0];
	const char *address = "bug-gawk@gnu.org";
	const char *editor;
	const char *tmpdir;
	const char *mailer;
	char uname_output[512] = "";
	char dead_letter[PATH_MAX];
	int sendmail = 0, do_help = 0, do_version = 0, index = 1;
	struct utsname name;
	const char *old_path = getenv("PATH");
	char *configured_path;

	if (asprintf(&configured_path, "/bin:/usr/bin:/usr/local/bin:%s",
	    old_path != NULL ? old_path : "") >= 0) {
		setenv("PATH", configured_path, 1);
		free(configured_path);
	}

	while (index < argc) {
		if (strcmp(argv[index], "--help") == 0)
			do_help = 1;
		else if (strcmp(argv[index], "--version") == 0)
			do_version = 1;
		else if (strcmp(argv[index], "--") == 0) {
			index++;
			break;
		} else if (argv[index][0] == '-') {
			fprintf(stderr, "gawkbug: %s: invalid option\n", argv[index]);
			fprintf(stderr, "Usage: %s [--help] [--version] [bug-report-email-address]\n",
			    program);
			return 2;
		} else
			break;
		index++;
	}
	if (do_version) {
		printf("GNU gawkbug, version %s\n", GAWKBUG_VERSION);
		return 0;
	}
	if (do_help) {
		print_help(program);
		return 0;
	}
	if (index < argc)
		address = argv[index];

	tmpdir = getenv("TMPDIR");
	if (tmpdir == NULL || *tmpdir == '\0')
		tmpdir = "/tmp";
	if (snprintf(temporary_directory, sizeof temporary_directory,
	    "%s/gbug.%ld", tmpdir, (long) getpid()) >=
	    (int) sizeof temporary_directory || mkdir(temporary_directory, 0700) != 0) {
		fprintf(stderr, "%s: could not create temporary directory\n", program);
		temporary_directory[0] = '\0';
		return 1;
	}
	{
		size_t directory_length = strlen(temporary_directory);
		if (directory_length > sizeof temporary_report - sizeof "/gbug1") {
			rmdir(temporary_directory);
			temporary_directory[0] = '\0';
			fprintf(stderr, "%s: could not create temporary directory\n", program);
			return 1;
		}
		memcpy(temporary_report, temporary_directory, directory_length);
		memcpy(temporary_report + directory_length, "/gbug1", sizeof "/gbug1");
		memcpy(temporary_original, temporary_directory, directory_length);
		memcpy(temporary_original + directory_length, "/gbug2", sizeof "/gbug2");
	}
	atexit(remove_temporary_directory);
	signal(SIGHUP, handle_signal);
	signal(SIGINT, handle_signal);
	signal(SIGQUIT, handle_signal);
	signal(SIGPIPE, handle_signal);
	signal(SIGTERM, handle_signal);
	if (uname(&name) == 0)
		snprintf(uname_output, sizeof uname_output,
		    "%s %s %s %s %s %s %s GNU/Linux",
		    name.sysname, name.nodename, name.release, name.version,
		    name.machine, name.machine, name.machine);
	if (write_template(temporary_report, current_user(), address, uname_output) != 0 ||
	    copy_file(temporary_report, temporary_original) != 0) {
		fprintf(stderr, "%s: could not create bug report template\n", program);
		return 1;
	}
	editor = select_editor();
	for (;;) {
		int status;
		signal(SIGINT, SIG_IGN);
		status = run_editor(editor, temporary_report);
		signal(SIGINT, handle_signal);
		if (status != 0) {
			printf("%s: editor `%s' exited with nonzero status.\n", program, editor);
			printf("%s: Perhaps it was interrupted.\n", program);
			printf("%s: Type `y' to give up, and lose your bug report;\n", program);
			printf("%s: type `n' to re-enter the editor.\n", program);
			printf("%s: Do you want to give up? ", program);
			fflush(stdout);
			{
				int answer = read_answer();
				if (answer == 'y' || answer == 'Y')
					return 1;
			}
			continue;
		}
		if (!subject_is_default(temporary_report))
			break;
		printf("\n%s: You have not changed the subject from the default.\n", program);
		printf("%s: Please use a more descriptive subject header.\n", program);
		printf("%s: Type `y' to give up, and lose your bug report;\n", program);
		printf("%s: type `n' to re-enter the editor.\n", program);
		printf("%s: Do you want to give up? ", program);
		fflush(stdout);
		{
			int answer = read_answer();
			if (answer == 'y' || answer == 'Y')
				return 1;
		}
		printf("%s:  The editor will be restarted in five seconds.\n", program);
		sleep(5);
	}
	if (files_equal(temporary_report, temporary_original)) {
		puts("File not changed, no bug report submitted.");
		return 0;
	}
	printf("Send bug report to %s? [y/n] ", address);
	fflush(stdout);
	{
		int answer = read_answer();
		if (answer == 'n' || answer == 'N')
			return 0;
	}
	if (access("/usr/lib/sendmail", F_OK) == 0) {
		mailer = "/usr/lib/sendmail";
		sendmail = 1;
	} else if (access("/usr/sbin/sendmail", F_OK) == 0) {
		mailer = "/usr/sbin/sendmail";
		sendmail = 1;
	} else
		mailer = "rmail";
	if (run_mailer(mailer, sendmail, address, temporary_report) != 0) {
		const char *home = getenv("HOME");
		int source, destination;
		char buffer[8192];
		ssize_t count;
		if (home == NULL || *home == '\0')
			home = ".";
		snprintf(dead_letter, sizeof dead_letter, "%s/dead.gawkbug", home);
		source = open(temporary_report, O_RDONLY);
		destination = open(dead_letter, O_WRONLY | O_CREAT | O_APPEND, 0600);
		if (source >= 0 && destination >= 0)
			while ((count = read(source, buffer, sizeof buffer)) > 0)
				(void) write(destination, buffer, (size_t) count);
		if (source >= 0)
			close(source);
		if (destination >= 0)
			close(destination);
		fprintf(stderr, "%s: mail to %s failed: report saved in %s\n",
		    program, address, dead_letter);
		fprintf(stderr, "%s: please send it manually to %s\n", program, address);
	}
	return 0;
}
