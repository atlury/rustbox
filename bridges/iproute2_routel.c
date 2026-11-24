/* SPDX-License-Identifier: GPL-2.0 */
/* Native form of IPRoute2 7.3.0's ip/routel Python frontend. */

#define _GNU_SOURCE 1

#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef RUSTBOX_ROUTEL_IP_MAIN
#define RUSTBOX_ROUTEL_IP_MAIN rustbox_iproute2_ip_main
#endif

extern int RUSTBOX_ROUTEL_IP_MAIN(int, char **);

#if defined(__GLIBC__)
extern char *program_invocation_name;
extern char *program_invocation_short_name;
#endif

struct text {
	char *data;
	size_t length;
	size_t capacity;
};

struct value {
	char *text;
	int string;
};

struct route {
	struct value field[7];
};

struct routes {
	struct route *item;
	size_t length;
	size_t capacity;
};

struct parser {
	const unsigned char *current;
	const unsigned char *end;
};

static const char *const route_key[7] = {
	"dst", "gateway", "prefsrc", "protocol", "scope", "dev", "table"
};

static int
text_reserve(struct text *text, size_t extra)
{
	size_t needed = text->length + extra + 1;
	size_t capacity = text->capacity == 0 ? 64 : text->capacity;
	char *data;

	if (text->data != NULL && needed <= text->capacity)
		return 0;
	while (capacity < needed) {
		if (capacity > SIZE_MAX / 2)
			return -1;
		capacity *= 2;
	}
	data = realloc(text->data, capacity);
	if (data == NULL)
		return -1;
	text->data = data;
	text->capacity = capacity;
	return 0;
}

static int
text_append(struct text *text, const void *source, size_t length)
{
	if (length == 0)
		return 0;
	if (text_reserve(text, length) != 0)
		return -1;
	memcpy(text->data + text->length, source, length);
	text->length += length;
	text->data[text->length] = '\0';
	return 0;
}

static int
text_byte(struct text *text, unsigned char byte)
{
	return text_append(text, &byte, 1);
}

static void
skip_space(struct parser *parser)
{
	while (parser->current < parser->end &&
	    (*parser->current == ' ' || *parser->current == '\t' ||
	    *parser->current == '\n' || *parser->current == '\r'))
		++parser->current;
}

static int
hex_digit(unsigned char value)
{
	if ('0' <= value && value <= '9')
		return value - '0';
	if ('a' <= value && value <= 'f')
		return value - 'a' + 10;
	if ('A' <= value && value <= 'F')
		return value - 'A' + 10;
	return -1;
}

static int
unicode_escape(struct parser *parser, uint32_t *value)
{
	uint32_t result = 0;
	int digit;
	int index;

	if ((size_t)(parser->end - parser->current) < 4)
		return -1;
	for (index = 0; index < 4; ++index) {
		digit = hex_digit(*parser->current++);
		if (digit < 0)
			return -1;
		result = result * 16 + (uint32_t)digit;
	}
	*value = result;
	return 0;
}

static int
append_utf8(struct text *text, uint32_t value)
{
	unsigned char encoded[4];
	size_t length;

	if (value <= 0x7f) {
		encoded[0] = (unsigned char)value;
		length = 1;
	} else if (value <= 0x7ff) {
		encoded[0] = 0xc0 | (unsigned char)(value >> 6);
		encoded[1] = 0x80 | (unsigned char)(value & 0x3f);
		length = 2;
	} else if (value <= 0xffff) {
		if (0xd800 <= value && value <= 0xdfff)
			return -1;
		encoded[0] = 0xe0 | (unsigned char)(value >> 12);
		encoded[1] = 0x80 | (unsigned char)((value >> 6) & 0x3f);
		encoded[2] = 0x80 | (unsigned char)(value & 0x3f);
		length = 3;
	} else if (value <= 0x10ffff) {
		encoded[0] = 0xf0 | (unsigned char)(value >> 18);
		encoded[1] = 0x80 | (unsigned char)((value >> 12) & 0x3f);
		encoded[2] = 0x80 | (unsigned char)((value >> 6) & 0x3f);
		encoded[3] = 0x80 | (unsigned char)(value & 0x3f);
		length = 4;
	} else {
		return -1;
	}
	return text_append(text, encoded, length);
}

static int
parse_string(struct parser *parser, struct text *output)
{
	uint32_t first;
	uint32_t second;
	unsigned char value;

	if (parser->current == parser->end || *parser->current++ != '"')
		return -1;
	while (parser->current < parser->end) {
		value = *parser->current++;
		if (value == '"')
			return 0;
		if (value < 0x20)
			return -1;
		if (value != '\\') {
			if (text_byte(output, value) != 0)
				return -1;
			continue;
		}
		if (parser->current == parser->end)
			return -1;
		value = *parser->current++;
		switch (value) {
		case '"': case '\\': case '/':
			if (text_byte(output, value) != 0)
				return -1;
			break;
		case 'b': if (text_byte(output, '\b') != 0) return -1; break;
		case 'f': if (text_byte(output, '\f') != 0) return -1; break;
		case 'n': if (text_byte(output, '\n') != 0) return -1; break;
		case 'r': if (text_byte(output, '\r') != 0) return -1; break;
		case 't': if (text_byte(output, '\t') != 0) return -1; break;
		case 'u':
			if (unicode_escape(parser, &first) != 0)
				return -1;
			if (0xd800 <= first && first <= 0xdbff) {
				if ((size_t)(parser->end - parser->current) < 6 ||
				    parser->current[0] != '\\' || parser->current[1] != 'u')
					return -1;
				parser->current += 2;
				if (unicode_escape(parser, &second) != 0 ||
				    second < 0xdc00 || 0xdfff < second)
					return -1;
				first = 0x10000 + ((first - 0xd800) << 10) +
				    (second - 0xdc00);
			}
			if (append_utf8(output, first) != 0)
				return -1;
			break;
		default:
			return -1;
		}
	}
	return -1;
}

static int skip_value(struct parser *);

static int
skip_array(struct parser *parser)
{
	if (*parser->current++ != '[')
		return -1;
	skip_space(parser);
	if (parser->current < parser->end && *parser->current == ']') {
		++parser->current;
		return 0;
	}
	for (;;) {
		if (skip_value(parser) != 0)
			return -1;
		skip_space(parser);
		if (parser->current == parser->end)
			return -1;
		if (*parser->current == ']') {
			++parser->current;
			return 0;
		}
		if (*parser->current++ != ',')
			return -1;
		skip_space(parser);
	}
}

static int
skip_object(struct parser *parser)
{
	struct text key = {0};

	if (*parser->current++ != '{')
		return -1;
	skip_space(parser);
	if (parser->current < parser->end && *parser->current == '}') {
		++parser->current;
		return 0;
	}
	for (;;) {
		key.length = 0;
		if (parse_string(parser, &key) != 0)
			goto failure;
		skip_space(parser);
		if (parser->current == parser->end || *parser->current++ != ':')
			goto failure;
		skip_space(parser);
		if (skip_value(parser) != 0)
			goto failure;
		skip_space(parser);
		if (parser->current == parser->end)
			goto failure;
		if (*parser->current == '}') {
			++parser->current;
			free(key.data);
			return 0;
		}
		if (*parser->current++ != ',')
			goto failure;
		skip_space(parser);
	}
failure:
	free(key.data);
	return -1;
}

static int
skip_value(struct parser *parser)
{
	struct text string = {0};
	const unsigned char *start;

	skip_space(parser);
	if (parser->current == parser->end)
		return -1;
	if (*parser->current == '"') {
		int result = parse_string(parser, &string);
		free(string.data);
		return result;
	}
	if (*parser->current == '[')
		return skip_array(parser);
	if (*parser->current == '{')
		return skip_object(parser);
	start = parser->current;
	while (parser->current < parser->end &&
	    strchr("-+0123456789.eEabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
	    *parser->current) != NULL)
		++parser->current;
	return parser->current == start ? -1 : 0;
}

static int
key_index(const char *key)
{
	int index;

	for (index = 0; index < 7; ++index)
		if (strcmp(key, route_key[index]) == 0)
			return index;
	return -1;
}

static int
parse_field_value(struct parser *parser, struct value *value)
{
	const unsigned char *start;
	const unsigned char *finish;
	struct text decoded = {0};
	size_t length;

	skip_space(parser);
	if (parser->current == parser->end)
		return -1;
	if (*parser->current == '"') {
		if (parse_string(parser, &decoded) != 0) {
			free(decoded.data);
			return -1;
		}
		if (decoded.data == NULL)
			decoded.data = strdup("");
		if (decoded.data == NULL)
			return -1;
		free(value->text);
		value->text = decoded.data;
		value->string = 1;
		return 0;
	}
	start = parser->current;
	if (skip_value(parser) != 0)
		return -1;
	finish = parser->current;
	while (finish > start && strchr(" \t\r\n", finish[-1]) != NULL)
		--finish;
	length = (size_t)(finish - start);
	decoded.data = malloc(length + 1);
	if (decoded.data == NULL)
		return -1;
	memcpy(decoded.data, start, length);
	decoded.data[length] = '\0';
	if (strcmp(decoded.data, "true") == 0)
		strcpy(decoded.data, "True");
	else if (strcmp(decoded.data, "false") == 0)
		strcpy(decoded.data, "False");
	else if (strcmp(decoded.data, "null") == 0)
		strcpy(decoded.data, "None");
	free(value->text);
	value->text = decoded.data;
	value->string = 0;
	return 0;
}

static void
free_route(struct route *route)
{
	int index;

	for (index = 0; index < 7; ++index)
		free(route->field[index].text);
}

static int
append_route(struct routes *routes, struct route *route)
{
	struct route *items;
	size_t capacity;

	if (routes->length == routes->capacity) {
		capacity = routes->capacity == 0 ? 16 : routes->capacity * 2;
		if (capacity < routes->capacity)
			return -1;
		items = realloc(routes->item, capacity * sizeof(*items));
		if (items == NULL)
			return -1;
		routes->item = items;
		routes->capacity = capacity;
	}
	routes->item[routes->length++] = *route;
	memset(route, 0, sizeof(*route));
	return 0;
}

static int
parse_route(struct parser *parser, struct route *route)
{
	struct text key = {0};
	int index;

	if (parser->current == parser->end || *parser->current++ != '{')
		return -1;
	skip_space(parser);
	if (parser->current < parser->end && *parser->current == '}') {
		++parser->current;
		return 0;
	}
	for (;;) {
		key.length = 0;
		if (key.data != NULL)
			key.data[0] = '\0';
		if (parse_string(parser, &key) != 0)
			goto failure;
		skip_space(parser);
		if (parser->current == parser->end || *parser->current++ != ':')
			goto failure;
		skip_space(parser);
		index = key_index(key.data == NULL ? "" : key.data);
		if (index < 0) {
			if (skip_value(parser) != 0)
				goto failure;
		} else if (parse_field_value(parser, &route->field[index]) != 0) {
			goto failure;
		}
		skip_space(parser);
		if (parser->current == parser->end)
			goto failure;
		if (*parser->current == '}') {
			++parser->current;
			free(key.data);
			return 0;
		}
		if (*parser->current++ != ',')
			goto failure;
		skip_space(parser);
	}
failure:
	free(key.data);
	return -1;
}

static int
parse_routes(const char *json, size_t length, struct routes *routes)
{
	struct parser parser = {
		.current = (const unsigned char *)json,
		.end = (const unsigned char *)json + length,
	};
	struct route route = {0};

	skip_space(&parser);
	if (parser.current == parser.end || *parser.current++ != '[')
		return -1;
	skip_space(&parser);
	if (parser.current < parser.end && *parser.current == ']') {
		++parser.current;
		skip_space(&parser);
		return parser.current == parser.end ? 0 : -1;
	}
	for (;;) {
		memset(&route, 0, sizeof(route));
		if (parse_route(&parser, &route) != 0 || append_route(routes, &route) != 0) {
			free_route(&route);
			return -1;
		}
		skip_space(&parser);
		if (parser.current == parser.end)
			return -1;
		if (*parser.current == ']') {
			++parser.current;
			skip_space(&parser);
			return parser.current == parser.end ? 0 : -1;
		}
		if (*parser.current++ != ',')
			return -1;
		skip_space(&parser);
	}
}

static void
free_routes(struct routes *routes)
{
	size_t index;

	for (index = 0; index < routes->length; ++index)
		free_route(&routes->item[index]);
	free(routes->item);
}

#if defined(__GNUC__) && !defined(__clang__)
/* GCC 15 treats a successful dup2 onto the deliberately persistent stdout
 * descriptor as a newly leaked descriptor.  Both replacements are closed by
 * the next dup2 or process teardown; saved_stdout and the temporary stream are
 * closed explicitly on every path. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wanalyzer-fd-leak"
#endif
static int
capture_ip(int argc, char **argv, struct text *json)
{
	FILE *temporary;
	int saved_stdout;
	int saved_optind;
	int saved_opterr;
	int saved_optopt;
	char *saved_optarg;
#if defined(__GLIBC__)
	char *saved_program_name;
	char *saved_program_short_name;
#endif
	int status;
	char buffer[16384];
	size_t length;

	if (fflush(stdout) != 0)
		return -1;
	temporary = tmpfile();
	if (temporary == NULL)
		return -1;
	saved_stdout = dup(STDOUT_FILENO);
	if (saved_stdout < 0) {
		fclose(temporary);
		return -1;
	}
	if (dup2(fileno(temporary), STDOUT_FILENO) < 0) {
		close(saved_stdout);
		fclose(temporary);
		return -1;
	}
	saved_optind = optind;
	saved_opterr = opterr;
	saved_optopt = optopt;
	saved_optarg = optarg;
	optind = 1;
	opterr = 1;
	optopt = 0;
	optarg = NULL;
#if defined(__GLIBC__)
	saved_program_name = program_invocation_name;
	saved_program_short_name = program_invocation_short_name;
	program_invocation_name = argv[0];
	program_invocation_short_name = argv[0];
#endif
	status = RUSTBOX_ROUTEL_IP_MAIN(argc, argv);
	optind = saved_optind;
	opterr = saved_opterr;
	optopt = saved_optopt;
	optarg = saved_optarg;
#if defined(__GLIBC__)
	program_invocation_name = saved_program_name;
	program_invocation_short_name = saved_program_short_name;
#endif
	if (fflush(stdout) != 0)
		status = -1;
	if (dup2(saved_stdout, STDOUT_FILENO) < 0)
		status = -1;
	close(saved_stdout);
	clearerr(stdout);
	if (fseek(temporary, 0, SEEK_SET) != 0)
		status = -1;
	while (status >= 0 && (length = fread(buffer, 1, sizeof(buffer), temporary)) != 0)
		if (text_append(json, buffer, length) != 0)
			status = -1;
	if (ferror(temporary))
		status = -1;
	fclose(temporary);
	return status < 0 ? -1 : 0;
}
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic pop
#endif

static const char *
field_text(const struct value *value)
{
	return value->text == NULL ? "" : value->text;
}

static void
print_width(const struct value *value, int width, int force_left)
{
	const char *text = field_text(value);
	const unsigned char *cursor = (const unsigned char *)text;
	int used = 0;
	int padding;

	while (*cursor != '\0') {
		if ((*cursor & 0xc0) != 0x80)
			++used;
		++cursor;
	}
	padding = width > used ? width - used : 0;

	if (!force_left && value->text != NULL && !value->string)
		while (padding-- > 0)
			putchar(' ');
	fputs(text, stdout);
	if (force_left || value->text == NULL || value->string)
		while (padding-- > 0)
			putchar(' ');
}

static void
print_routes(const struct routes *routes, int width)
{
	struct route heading = {0};
	static char *const heading_text[7] = {
		"Dst", "Gateway", "Prefsrc", "Protocol", "Scope", "Dev", "Table"
	};
	size_t record;
	int index;

	for (index = 0; index < 7; ++index) {
		heading.field[index].text = heading_text[index];
		heading.field[index].string = 1;
	}
	for (record = 0; record <= routes->length; ++record) {
		const struct route *route = record == 0 ? &heading : &routes->item[record - 1];
		print_width(&route->field[0], width, 0); putchar(' ');
		print_width(&route->field[1], width, 0); putchar(' ');
		print_width(&route->field[2], width, 0); putchar(' ');
		print_width(&route->field[3], 8, 0); putchar(' ');
		print_width(&route->field[4], 8, 0);
		print_width(&route->field[5], 16, 1); putchar(' ');
		fputs(field_text(&route->field[6]), stdout);
		putchar('\n');
	}
}

static int
usage(const char *program)
{
	printf("Usage: %s [tablenr [raw ip args...]]\n",
	    program == NULL ? "routel" : program);
	return 64;
}

struct parsed_option {
	char name;
	const char *argument;
};

int
rustbox_iproute2_routel_main(int argc, char **argv)
{
	struct parsed_option options[64];
	int option_count = 0;
	int argument = 1;
	const char *family = "inet";
	struct text json = {0};
	struct routes routes = {0};
	char **ip_argv;
	int ip_argc;
	int trailing;
	int index;

	while (argument < argc && argv[argument][0] == '-' && argv[argument][1] != '\0') {
		const char *token = argv[argument];
		if (strcmp(token, "--") == 0) {
			++argument;
			break;
		}
		if (token[1] == '-') {
			const char *name = token + 2;
			const char *equals = strchr(name, '=');
			size_t name_length = equals == NULL ? strlen(name) : (size_t)(equals - name);
			int is_help = name_length != 0 && strncmp("help", name, name_length) == 0;
			int is_family = name_length != 0 && strncmp("family", name, name_length) == 0;
			if (is_help && is_family) {
				printf("option --%.*s not a unique prefix\n", (int)name_length, name);
				return usage(argv[0]);
			}
			if (is_help) {
				if (equals != NULL) {
					printf("option --help must not have an argument\n");
					return usage(argv[0]);
				}
				if (option_count >= (int)(sizeof(options) / sizeof(options[0]))) {
					fputs("routel: too many options\n", stderr);
					return 1;
				}
				options[option_count++] = (struct parsed_option){'h', NULL};
			} else if (is_family) {
				const char *value = equals == NULL ? NULL : equals + 1;
				if (value == NULL && ++argument < argc)
					value = argv[argument];
				if (value == NULL) {
					printf("option --family requires argument\n");
					return usage(argv[0]);
				}
				if (option_count >= (int)(sizeof(options) / sizeof(options[0]))) {
					fputs("routel: too many options\n", stderr);
					return 1;
				}
				options[option_count++] = (struct parsed_option){'f', value};
			} else {
				printf("option --%.*s not recognized\n", (int)name_length, name);
				return usage(argv[0]);
			}
			++argument;
			continue;
		}
		for (index = 1; token[index] != '\0'; ++index) {
			char option = token[index];
			if (option_count >= (int)(sizeof(options) / sizeof(options[0]))) {
				fputs("routel: too many options\n", stderr);
				return 1;
			}
			if (option == 'h' || option == '4' || option == '6') {
				options[option_count++] = (struct parsed_option){option, NULL};
			} else if (option == 'f') {
				const char *value = token[index + 1] == '\0' ? NULL : token + index + 1;
				if (value == NULL && ++argument < argc)
					value = argv[argument];
				if (value == NULL) {
					printf("option -f requires argument\n");
					return usage(argv[0]);
				}
				options[option_count++] = (struct parsed_option){'f', value};
				break;
			} else {
				printf("option -%c not recognized\n", option);
				return usage(argv[0]);
			}
		}
		++argument;
	}
	for (index = 0; index < option_count; ++index) {
		if (options[index].name == 'h')
			return usage(argv[0]);
		if (options[index].name == '4')
			family = "inet";
		else if (options[index].name == '6')
			family = "inet6";
		else if (options[index].name == 'f')
			family = options[index].argument;
	}
	trailing = argc - argument;
	if (trailing == 0)
		trailing = 1;
	ip_argc = 7 + trailing;
	ip_argv = calloc((size_t)ip_argc + 1, sizeof(*ip_argv));
	if (ip_argv == NULL)
		return 1;
	ip_argv[0] = "ip";
	ip_argv[1] = "-f";
	ip_argv[2] = (char *)family;
	ip_argv[3] = "-j";
	ip_argv[4] = "route";
	ip_argv[5] = "list";
	ip_argv[6] = "table";
	if (argument == argc)
		ip_argv[7] = "0";
	else
		for (index = argument; index < argc; ++index)
			ip_argv[7 + index - argument] = argv[index];
	if (capture_ip(ip_argc, ip_argv, &json) != 0) {
		free(ip_argv);
		free(json.data);
		fputs("routel: could not capture ip route output\n", stderr);
		return 1;
	}
	free(ip_argv);
	if (parse_routes(json.data == NULL ? "" : json.data, json.length, &routes) != 0) {
		free(json.data);
		free_routes(&routes);
		fputs("routel: invalid ip route JSON\n", stderr);
		return 1;
	}
	free(json.data);
	print_routes(&routes, strcmp(family, "inet") == 0 ? 15 : 32);
	free_routes(&routes);
	return 0;
}

#ifndef RUSTBOX_MULTICALL
int
main(int argc, char **argv)
{
	return rustbox_iproute2_routel_main(argc, argv);
}
#endif
