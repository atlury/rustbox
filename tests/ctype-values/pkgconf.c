/* SPDX-License-Identifier: ISC */
#define _GNU_SOURCE
#include <locale.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int pkgconf_argv_split(const char *, int *, char ***);
extern int pkgconf_argv_split_raw(const char *, int *, char ***);
extern void pkgconf_argv_free(char **);
typedef void (*operand)(void *, const char *, const char *, const char *);
typedef void (*warning)(void *, const char *, ...);
extern void pkgconf_parser_parse(FILE *, void *, const operand *, warning, const char *);

static void text(const char *s) {
    size_t n = strlen(s);
    if (n > UINT16_MAX) abort();
    uint16_t len = (uint16_t)n;
    if (fwrite(&len, sizeof len, 1, stdout) != 1 || fwrite(s, 1, n, stdout) != n) abort();
}

static void record(void *ctx, const char *prefix, const char *key, const char *value) {
    (void)ctx;
    putchar('K'); text(prefix); text(key); text(value);
}
static void warn(void *ctx, const char *format, ...) {
    (void)ctx;
    char buf[512];
    va_list ap;
    va_start(ap, format);
    int n = vsnprintf(buf, sizeof buf, format, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= sizeof buf) abort();
    putchar('W'); text(buf);
}

int main(int argc, char **argv) {
    operand ops[256] = {0};
    ops['='] = ops[':'] = record;
    for (int i = 1; i < argc; ++i) {
        if (!setlocale(LC_CTYPE, argv[i])) return 2;
        for (int b = 0; b <= 255; ++b) {
            char templates[][32] = {"x?y z", "'x?y' z", "\"x?y\" z", "x\\?y z", "?x 'unfinished"};
            for (size_t j = 0; j < sizeof templates / sizeof templates[0]; ++j) {
                char *mark = strchr(templates[j], '?');
                *mark = (char)b;
                for (int raw = 0; raw <= 1; ++raw) {
                    int count = -1;
                    char **args = NULL;
                    int status = (raw ? pkgconf_argv_split_raw : pkgconf_argv_split)(templates[j], &count, &args);
                    if (status == 0) {
                        if (!args || count < 0 || count > 5) return 3;
                        putchar('A'); putchar(count);
                        for (int k = 0; k < count; ++k) text(args[k]);
                        pkgconf_argv_free(args);
                    } else {
                        if (status != -1 || args) return 4;
                        putchar('E');
                    }
                }
            }
            unsigned char pc[] = "?Key: value\nK?2 = ?v?\nName: end\n";
            for (size_t k = 0; k < sizeof pc - 1; ++k)
                if (pc[k] == '?') pc[k] = (unsigned char)b;
            FILE *file = fmemopen(pc, sizeof pc - 1, "r");
            if (!file) return 5;
            pkgconf_parser_parse(file, NULL, ops, warn, "fixture.pc");
            if (fclose(file)) return 6;
            putchar('Z');
        }
    }
    return fflush(stdout) != 0;
}
