/* SPDX-License-Identifier: GPL-3.0-or-later */

extern int wctob(unsigned int wc);

/* Gnulib declares the system wctob through an asm-labelled alias.  C2Rust
   preserves the C identifier but not the asm label, so provide the exact
   configured alias at the ABI boundary without editing generated Rust.  */
int
__wctob_alias(unsigned int wc)
{
	return wctob(wc);
}
