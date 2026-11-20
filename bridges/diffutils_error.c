/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern char *program_invocation_name;

/* Keep Diffutils on the libc error(3) policy even when another translated
   package provides the multicall process-global error symbol. */
void
rustbox_diffutils_error(int status, int errnum, const char *format, ...)
{
	va_list arguments;

	fflush(stdout);
	fprintf(stderr, "%s: ", program_invocation_name);
	va_start(arguments, format);
	vfprintf(stderr, format, arguments);
	va_end(arguments);
	if (errnum != 0)
		fprintf(stderr, ": %s", strerror(errnum));
	fputc('\n', stderr);
	if (status != 0)
		exit(status);
}
