/* SPDX-License-Identifier: ISC */

#include <stdio.h>
#include <string.h>

extern int rustbox_pkgconf_main(int argc, char *argv[]);
extern int rustbox_bomtool_main(int argc, char *argv[]);
extern int rustbox_pccritic_main(int argc, char *argv[]);
extern int rustbox_spdxtool_main(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	const char *name = strrchr(argv[0], '/');
	name = name != NULL ? name + 1 : argv[0];

	if (!strcmp(name, "pkgconf") || !strcmp(name, "pkg-config"))
		return rustbox_pkgconf_main(argc, argv);
	if (!strcmp(name, "bomtool"))
		return rustbox_bomtool_main(argc, argv);
	if (!strcmp(name, "pccritic"))
		return rustbox_pccritic_main(argc, argv);
	if (!strcmp(name, "spdxtool"))
		return rustbox_spdxtool_main(argc, argv);

	fprintf(stderr, "pkgconf hybrid: unknown invocation name: %s\n", name);
	return 127;
}
