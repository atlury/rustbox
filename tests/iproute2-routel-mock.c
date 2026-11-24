/* SPDX-License-Identifier: GPL-2.0 */

#include <stdio.h>
#include <stdlib.h>

int
rustbox_iproute2_ip_main(int argc, char **argv)
{
	const char *json = getenv("RUSTBOX_ROUTEL_JSON");
	const char *log_path = getenv("RUSTBOX_ROUTEL_ARGV_LOG");
	FILE *log;
	int index;

	if (log_path != NULL) {
		log = fopen(log_path, "wb");
		if (log == NULL)
			return 1;
		for (index = 0; index < argc; ++index)
			fprintf(log, "%s%c", argv[index], index + 1 == argc ? '\n' : '\0');
		fclose(log);
	}
	fputs(json == NULL ? "[]" : json, stdout);
	return 0;
}
