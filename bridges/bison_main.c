/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef RUSTBOX_EMBEDDED
extern int rustbox_bison_engine_main(int, char **);
extern int rustbox_bison_resources_create(char **);
extern int rustbox_bison_resources_create_persistent(char **);
extern void rustbox_bison_resources_remove(char *);
extern char *program_invocation_name;
extern char *program_invocation_short_name;
#else
extern int rustbox_bison_main(int, char **);
#endif

#if defined(__GNUC__) || defined(__clang__)
# define RUSTBOX_ENTRY __attribute__((noinline, used, visibility("default")))
#else
# define RUSTBOX_ENTRY
#endif

#ifdef RUSTBOX_EMBEDDED
static void
restore_environment(const char *name, char *value, int existed)
{
	if (existed)
		(void) setenv(name, value, 1);
	else
		(void) unsetenv(name);
	free(value);
}

RUSTBOX_ENTRY int
rustbox_bison_main(int argc, char **argv)
{
	const char *current_data = getenv("BISON_PKGDATADIR");
	const char *current_m4 = getenv("M4");
	const char *current_program = getenv("BISON_PROGRAM_NAME");
	char *saved_data = current_data == NULL ? NULL : strdup(current_data);
	char *saved_m4 = current_m4 == NULL ? NULL : strdup(current_m4);
	char *directory = NULL;
	char *m4 = NULL;
	char *saved_invocation_name = program_invocation_name;
	char *saved_invocation_short_name = program_invocation_short_name;
	int status = 2;
	int environment_changed = 0;
	int program_name_changed = 0;
	int setup_failed = 1;
	int persistent = 0;
	int index;

	for (index = 1; index < argc; ++index)
		if (strcmp(argv[index], "--print-datadir") == 0) {
			persistent = 1;
			break;
		}

	if ((current_data != NULL && saved_data == NULL)
	    || (current_m4 != NULL && saved_m4 == NULL)
	    || (persistent
	        ? rustbox_bison_resources_create_persistent(&directory)
	        : rustbox_bison_resources_create(&directory)) != 0)
		goto fail;
	m4 = malloc(strlen(directory) + sizeof "/m4");
	if (m4 == NULL)
		goto fail;
	sprintf(m4, "%s/m4", directory);
	if (setenv("BISON_PKGDATADIR", directory, 1) != 0)
		goto fail;
	environment_changed = 1;
	if (setenv("M4", m4, 1) != 0)
		goto fail;
	if (current_program == NULL) {
		if (setenv("BISON_PROGRAM_NAME", argv[0], 1) != 0)
			goto fail;
		program_name_changed = 1;
	}
	setup_failed = 0;
	program_invocation_name = (char *) (current_program == NULL
	    ? argv[0] : current_program);
	program_invocation_short_name = program_invocation_name;
	status = rustbox_bison_engine_main(argc, argv);
fail:
	program_invocation_name = saved_invocation_name;
	program_invocation_short_name = saved_invocation_short_name;
	if (setup_failed)
		perror("bison: embedded resources");
	if (environment_changed) {
		restore_environment("BISON_PKGDATADIR", saved_data, current_data != NULL);
		restore_environment("M4", saved_m4, current_m4 != NULL);
	} else {
		free(saved_data);
		free(saved_m4);
	}
	if (program_name_changed)
		(void) unsetenv("BISON_PROGRAM_NAME");
	free(m4);
	if (persistent)
		free(directory);
	else
		rustbox_bison_resources_remove(directory);
	return status;
}
#endif

RUSTBOX_ENTRY int
rustbox_yacc_main(int argc, char **argv)
{
	char **compatibility_argv;
	int status;

	if (argc == INT_MAX || (size_t) argc > SIZE_MAX / sizeof(*argv) - 2)
		return 2;
	compatibility_argv = malloc(((size_t) argc + 2) * sizeof(*argv));
	if (compatibility_argv == NULL)
		return 2;
	compatibility_argv[0] = argv[0];
	compatibility_argv[1] = (char *) "-y";
	memcpy(compatibility_argv + 2, argv + 1,
	    (size_t) argc * sizeof(*argv));
	status = rustbox_bison_main(argc + 1, compatibility_argv);
	free(compatibility_argv);
	return status;
}

#ifndef RUSTBOX_MULTICALL
static const char *
base_name(const char *path)
{
	const char *slash = strrchr(path, '/');
	return slash == NULL ? path : slash + 1;
}

int
main(int argc, char **argv)
{
	if (strcmp(base_name(argv[0]), "yacc") == 0)
		return rustbox_yacc_main(argc, argv);
	return rustbox_bison_main(argc, argv);
}
#endif
