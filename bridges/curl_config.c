/* SPDX-License-Identifier: curl */

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char usage_text[] =
"Usage: curl-config [OPTION]\n"
"\n"
"Available values for OPTION include:\n"
"\n"
"  --built-shared        says 'yes' if libcurl was built shared\n"
"  --ca                  CA bundle install path\n"
"  --cc                  compiler\n"
"  --cflags              preprocessor and compiler flags\n"
"  --checkfor [version]  check for (lib)curl of the specified version\n"
"  --configure           the arguments given to configure when building curl\n"
"  --features            newline separated list of enabled features\n"
"  --help                display this help and exit\n"
"  --libs                library linking information\n"
"  --prefix              curl install prefix\n"
"  --protocols           newline separated list of enabled protocols\n"
"  --ssl-backends        output the SSL backends libcurl was built to support\n"
"  --static-libs         static libcurl library linking information\n"
"  --version             output version information\n"
"  --vernum              output version as a hexadecimal number\n";

static const char configure_arguments[] =
" '--disable-dependency-tracking' '--disable-shared' '--enable-static'"
" '--without-ssl' '--without-zlib' '--without-brotli' '--without-zstd'"
" '--without-libpsl' '--without-libgsasl' '--without-libssh2'"
" '--without-libssh' '--without-libidn2' '--without-nghttp2'"
" '--without-ngtcp2' '--without-nghttp3' '--without-quiche'"
" '--without-libuv' '--without-gssapi' '--disable-ldap' '--disable-ldaps'"
" '--without-ca-bundle' '--without-ca-path' '--without-ca-fallback'"
" '--without-ca-embed' 'CC=clang-18'"
" 'CFLAGS=-O2 -g -fno-omit-frame-pointer'";

static int
usage(int status)
{
	fputs(usage_text, stdout);
	return status;
}

static int
parse_component(const char **cursor, unsigned long *value, int final)
{
	char *end;

	if (!isdigit((unsigned char) **cursor))
		return -1;
	*value = strtoul(*cursor, &end, 10);
	if (end == *cursor)
		return -1;
	if (final) {
		if (*end != '\0' && *end != '-')
			return -1;
	}
	else if (*end != '.')
		return -1;
	*cursor = final ? end : end + 1;
	return 0;
}

static int
check_version(const char *requested)
{
	const char *cursor = requested;
	unsigned long major, minor, patch;

	if (requested == NULL
	    || parse_component(&cursor, &major, 0) != 0
	    || parse_component(&cursor, &minor, 0) != 0
	    || parse_component(&cursor, &patch, 1) != 0) {
		fprintf(stderr, "curl-config: invalid version: %s\n",
		    requested == NULL ? "" : requested);
		return 1;
	}
	if (major < 8 || (major == 8 && minor < 23)
	    || (major == 8 && minor == 23 && patch <= 0))
		return 0;
	printf("requested version %s is newer than existing 8.23.0\n", requested);
	return 1;
}

int
rustbox_curl_config_main(int argc, char *argv[])
{
	int index;

	if (argc == 1)
		return usage(1);
	for (index = 1; index < argc; ++index) {
		const char *option = argv[index];
		if (strcmp(option, "--built-shared") == 0)
			puts("no");
		else if (strcmp(option, "--ca") == 0)
			puts("");
		else if (strcmp(option, "--cc") == 0)
			puts("clang-18");
		else if (strcmp(option, "--prefix") == 0)
			puts("/usr/local");
		else if (strcmp(option, "--feature") == 0
		    || strcmp(option, "--features") == 0)
			fputs("alt-svc\nAsynchDNS\nIPv6\nLargefile\nthreadsafe\n"
			    "UnixSockets\n", stdout);
		else if (strcmp(option, "--protocols") == 0)
			fputs("DICT\nFILE\nFTP\nGOPHER\nHTTP\nIMAP\nIPFS\nIPNS\n"
			    "MQTT\nPOP3\nRTSP\nSMTP\nTELNET\nTFTP\nWS\n", stdout);
		else if (strcmp(option, "--version") == 0) {
			puts("libcurl 8.23.0");
			return 0;
		}
		else if (strcmp(option, "--checkfor") == 0)
			return check_version(index + 1 < argc ? argv[index + 1] : NULL);
		else if (strcmp(option, "--vernum") == 0) {
			puts("081700");
			return 0;
		}
		else if (strcmp(option, "--help") == 0)
			return usage(0);
		else if (strcmp(option, "--cflags") == 0)
			puts("-DCURL_STATICLIB -I/usr/local/include");
		else if (strcmp(option, "--libs") == 0)
			puts("-L/usr/local/lib -lcurl ");
		else if (strcmp(option, "--ssl-backends") == 0)
			puts("");
		else if (strcmp(option, "--static-libs") == 0)
			puts("/usr/local/lib/libcurl.a  ");
		else if (strcmp(option, "--configure") == 0)
			puts(configure_arguments);
		else {
			printf("unknown option: %s\n", option);
			return usage(1);
		}
	}
	return 0;
}

#ifndef RUSTBOX_MULTICALL
int
main(int argc, char *argv[])
{
	return rustbox_curl_config_main(argc, argv);
}
#endif
