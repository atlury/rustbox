/* SPDX-License-Identifier: 0BSD */

#include <string.h>

extern int rustbox_xz_main(int argc, char *argv[]);
extern int rustbox_xzdec_main(int argc, char *argv[]);
extern int rustbox_lzmadec_main(int argc, char *argv[]);
extern int rustbox_lzmainfo_main(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	const char *name = strrchr(argv[0], '/');
	name = name == NULL ? argv[0] : name + 1;
	if (strcmp(name, "xzdec") == 0)
		return rustbox_xzdec_main(argc, argv);
	if (strcmp(name, "lzmadec") == 0)
		return rustbox_lzmadec_main(argc, argv);
	if (strcmp(name, "lzmainfo") == 0)
		return rustbox_lzmainfo_main(argc, argv);
	return rustbox_xz_main(argc, argv);
}
