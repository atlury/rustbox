/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

extern int rustbox_bison_main(int, char **);

#if defined(__GNUC__) || defined(__clang__)
# define RUSTBOX_ENTRY __attribute__((noinline, used, visibility("default")))
#else
# define RUSTBOX_ENTRY
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
