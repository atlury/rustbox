/* SPDX-License-Identifier: X11 */
/*
 * Copyright 2018-2024,2025 Thomas E. Dickey
 * Copyright 2006-2015,2017 Free Software Foundation, Inc.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, distribute
 * with modifications, sublicense, and/or sell copies of the Software, and to
 * permit persons to whom the Software is furnished to do so, subject to the
 * following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * ABOVE COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR
 * IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 * Except as contained in this notice, the name(s) of the above copyright
 * holders shall not be used in advertising or otherwise to promote the sale,
 * use or other dealings in this Software without prior written authorization.
 */

/*
 * Native frontend for the configured Ncurses 6.6 ncursesw6-config script.
 *
 * The installed script contains no runtime discovery: all answers below are
 * configure-time values.  Keeping the frontend here makes those answers part
 * of the multicall executable and removes its dependency on /bin/sh, sed,
 * basename, and cat.
 */

#include <stdio.h>
#include <string.h>

static const char help_tail[] =
" [options]\n"
"\n"
"Options:\n"
"  --prefix            echoes the package-prefix of ncursesw\n"
"  --exec-prefix       echoes the executable-prefix of ncursesw\n"
"\n"
"  --cflags            echoes the C compiler flags needed to compile for ncursesw\n"
"  --cflags-only-I     echoes only -I C compiler flags needed with ncursesw\n"
"  --cflags-only-other echoes only C compiler flags other than -I for ncursesw\n"
"  --libs              echoes the libraries needed to link with ncursesw\n"
"\n"
"  --libs-only-L       echoes -L linker options (search path) for ncursesw\n"
"  --libs-only-l       echoes -l linker options (libraries) for ncursesw\n"
"  --libs-only-other   echoes linker options other than -L/-l\n"
"\n"
"  --version           echoes the release+patchdate version of ncursesw\n"
"  --abi-version       echoes the ABI version of ncursesw\n"
"  --mouse-version     echoes the mouse-interface version of ncursesw\n"
"\n"
"  --bindir            echoes the directory containing ncursesw programs\n"
"  --datadir           echoes the directory containing ncursesw data\n"
"  --includedir        echoes the directory containing ncursesw header files\n"
"  --libdir            echoes the directory containing ncursesw libraries\n"
"  --mandir            echoes the directory containing ncursesw man pages\n"
"  --terminfo          echoes the $TERMINFO terminfo database path\n"
"  --terminfo-dirs     echoes the $TERMINFO_DIRS directory list\n"
"  --termpath          echoes the $TERMPATH termcap list\n"
"\n"
"  --help              prints this message\n";

static const char *
base_name(const char *path)
{
	const char *slash;

	if (path == NULL)
		return "ncursesw6-config";
	slash = strrchr(path, '/');
	return slash == NULL ? path : slash + 1;
}

static void
print_help(FILE *stream, const char *program)
{
	fputs("Usage: ", stream);
	fputs(base_name(program), stream);
	fputs(help_tail, stream);
}

static const char *
answer(const char *option)
{
	if (strcmp(option, "--prefix") == 0 ||
	    strcmp(option, "--exec-prefix") == 0)
		return "/usr\n";
	if (strcmp(option, "--cflags") == 0 ||
	    strcmp(option, "--cflags-only-other") == 0)
		return "-D_DEFAULT_SOURCE -D_XOPEN_SOURCE=600\n";
	if (strcmp(option, "--cflags-only-I") == 0)
		return "\n";
	if (strcmp(option, "--libs") == 0 ||
	    strcmp(option, "--libs-only-l") == 0)
		return "-lncursesw -ltinfow\n";
	if (strcmp(option, "--libs-only-L") == 0 ||
	    strcmp(option, "--libs-only-other") == 0)
		return "\n";
	if (strcmp(option, "--version") == 0)
		return "6.6.20251230\n";
	if (strcmp(option, "--abi-version") == 0)
		return "6\n";
	if (strcmp(option, "--mouse-version") == 0)
		return "2\n";
	if (strcmp(option, "--bindir") == 0)
		return "/usr/bin\n";
	if (strcmp(option, "--datadir") == 0)
		return "/usr/share\n";
	if (strcmp(option, "--includedir") == 0)
		return "\n";
	if (strcmp(option, "--libdir") == 0)
		return "/usr/lib\n";
	if (strcmp(option, "--mandir") == 0)
		return "/usr/share/man\n";
	if (strcmp(option, "--terminfo") == 0 ||
	    strcmp(option, "--terminfo-dirs") == 0)
		return "/usr/share/terminfo\n";
	if (strcmp(option, "--termpath") == 0)
		return "\n";
	return NULL;
}

int
rustbox_ncursesw6_config_main(int argc, char **argv)
{
	int index;

	if (argc <= 1) {
		print_help(stderr, argc > 0 ? argv[0] : NULL);
		return 1;
	}
	for (index = 1; index < argc; ++index) {
		const char *value = answer(argv[index]);

		if (value != NULL) {
			fputs(value, stdout);
		} else if (strcmp(argv[index], "--help") == 0) {
			print_help(stdout, argv[0]);
		} else {
			print_help(stderr, argv[0]);
			return 1;
		}
	}
	return 0;
}

#ifndef RUSTBOX_MULTICALL
int
main(int argc, char **argv)
{
	return rustbox_ncursesw6_config_main(argc, argv);
}
#endif
