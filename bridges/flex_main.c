/* SPDX-License-Identifier: 0BSD */
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

extern int rustbox_flex_main(int, char **);

#if defined(__GNUC__) || defined(__clang__)
#define RUSTBOX_ENTRY __attribute__((noinline, used, visibility("default")))
#else
#define RUSTBOX_ENTRY
#endif

static const char *
base_name(const char *path)
{
	const char *slash = strrchr(path, '/');
	return slash == NULL ? path : slash + 1;
}

RUSTBOX_ENTRY int
rustbox_lex_main(int argc, char **argv)
{
	char **compatibility_argv;
	int status;

	if (argc == INT_MAX || (size_t) argc > SIZE_MAX / sizeof(*argv) - 2)
		return 2;
	compatibility_argv = malloc(((size_t) argc + 2) * sizeof(*argv));
	if (compatibility_argv == NULL)
		return 2;
	compatibility_argv[0] = argv[0];
	compatibility_argv[1] = (char *) "-l";
	memcpy(compatibility_argv + 2, argv + 1,
	    ((size_t) argc) * sizeof(*argv));
	status = rustbox_flex_main(argc + 1, compatibility_argv);
	free(compatibility_argv);
	return status;
}

RUSTBOX_ENTRY int
rustbox_flexpp_main(int argc, char **argv)
{
	return rustbox_flex_main(argc, argv);
}

#ifndef RUSTBOX_MULTICALL
int
main(int argc, char **argv)
{
	const char *name = base_name(argv[0]);

	if (strcmp(name, "lex") == 0)
		return rustbox_lex_main(argc, argv);
	if (strcmp(name, "flex++") == 0)
		return rustbox_flexpp_main(argc, argv);
	return rustbox_flex_main(argc, argv);
}
#endif
