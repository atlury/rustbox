/* SPDX-License-Identifier: GPL-3.0-or-later */

#include <wchar.h>

/* Gnulib declares these internal aliases so replacement functions can call
   the original libc entrypoints without macro recursion.  They are compiler
   aliases in C, but C2Rust preserves their ABI spellings as external calls. */
wint_t rustbox_btowc_alias(int byte) __asm__("__btowc_alias");
#ifndef RUSTBOX_BTOWC_ONLY
int rustbox_wctob_alias(wint_t character) __asm__("__wctob_alias");
#endif

wint_t
rustbox_btowc_alias(int byte)
{
	return btowc(byte);
}

#ifndef RUSTBOX_BTOWC_ONLY
int
rustbox_wctob_alias(wint_t character)
{
	return wctob(character);
}
#endif
