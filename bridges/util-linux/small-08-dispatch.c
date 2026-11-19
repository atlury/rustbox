/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <libgen.h>
#include <stdio.h>
#include <string.h>

extern char *program_invocation_name;
extern char *program_invocation_short_name;
extern int rustbox_setarch_main(int, char **);

static const char *const aliases[] = {
	"i386", "ia64", "linux32", "linux64", "mips", "mips32", "mips64",
	"parisc", "parisc32", "parisc64", "ppc", "ppc32", "ppc64", "s390",
	"s390x", "setarch", "sparc", "sparc32", "sparc32bash", "sparc64",
	"uname26", "x86_64"
};

static int dispatch(const char *name, int argc, char **argv)
{
	size_t index;

	for (index = 0; index < sizeof(aliases) / sizeof(aliases[0]); index++)
		if (strcmp(name, aliases[index]) == 0)
			return rustbox_setarch_main(argc, argv);
	errno = ENOENT;
	fprintf(stderr, "rustbox: unknown applet: %s\n", name);
	return 127;
}

int main(int argc, char **argv)
{
	char *name = basename(argv[0]);

	if (strcmp(name, "rustbox-util-linux-small-08") == 0) {
		if (argc < 2) {
			fputs("usage: rustbox-util-linux-small-08 APPLET [ARGUMENT]...\n", stderr);
			return 127;
		}
		argc--;
		argv++;
		name = basename(argv[0]);
		program_invocation_name = argv[0];
		program_invocation_short_name = basename(argv[0]);
	}
	return dispatch(name, argc, argv);
}
