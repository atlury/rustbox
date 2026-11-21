/* SPDX-License-Identifier: GPL-3.0-or-later */

#include <wchar.h>

/* Gnulib declares these internal aliases so replacement functions can call
   the original libc entrypoints without macro recursion.  They are compiler
   aliases in C, but C2Rust preserves their ABI spellings as external calls. */
wint_t rustbox_btowc_alias(int byte) __asm__("__btowc_alias");
int rustbox_wctob_alias(wint_t character) __asm__("__wctob_alias");

wint_t
rustbox_btowc_alias(int byte)
{
	return btowc(byte);
}

int
rustbox_wctob_alias(wint_t character)
{
	return wctob(character);
}

extern int rustbox_grep_main(int argc, char *argv[]);

int
main(int argc, char *argv[])
{
	return rustbox_grep_main(argc, argv);
}
