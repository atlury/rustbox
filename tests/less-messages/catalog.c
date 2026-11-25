/* SPDX-License-Identifier: 0BSD */
#include <stdio.h>
#include <string.h>

extern void lmsg_init(const char *);
extern const char *lmsg(unsigned);
extern char *help_data;
extern int size_help_data;

#define M(sym, text) #sym,
static const char *const names[] = {
#include "lessmsg.inc"
};
#undef M
#define M(sym, text) text,
static const char *const defaults[] = {
#include "lessmsg.inc"
};
#undef M

enum { COUNT = sizeof(names)/sizeof(names[0]) };

static int print_bytes(const char *p, size_t len)
{
    if (!p) return 1;
    for (size_t i = 0; i < len; ++i) printf("%02x", (unsigned char)p[i]);
    putchar('\n');
    return 0;
}

int __wrap_main(void)
{
    const char *before[COUNT], *loaded[COUNT];
    lmsg_init(NULL);
    FILE *f = fopen("messages", "wb");
    if (!f) return 1;
    for (unsigned i = 0; i < COUNT; ++i) {
        before[i] = lmsg(i+1);
        if (!before[i] || strcmp(before[i], defaults[i])) return 2;
        fprintf(f, "%s entry-%u\\t\\377\\nX\n", names[i], i+1);
    }
    fputs("HELP help\\000discard\n", f);
    if (fclose(f)) return 3;
    lmsg_init("messages");
    for (unsigned i = 0; i < COUNT; ++i) {
        char expected[64];
        int len = snprintf(expected, sizeof(expected), "entry-%u\t\377\nX", i+1);
        loaded[i] = lmsg(i+1);
        if (!loaded[i] || strcmp(loaded[i], expected) || strcmp(before[i], defaults[i])) return 4;
        fprintf(stdout, "first %u ", i+1);
        if (print_bytes(loaded[i], (size_t)len)) return 5;
    }
    if (size_help_data != 12 || !help_data || memcmp(help_data, "help\0\0\0\0\0\0\0\0", 12)) return 6;
    f = fopen("overrides", "wb");
    if (!f) return 7;
    fprintf(f, "# selective reload\n%s first\n%s second\n%s \nHELP other\\nhelp\n", names[0], names[0], names[COUNT-1]);
    if (fclose(f)) return 8;
    lmsg_init("overrides");
    for (unsigned i = 0; i < COUNT; ++i) {
        const char *current = lmsg(i+1);
        if (!current || (i == 0 ? strcmp(current, "second") : i+1 == COUNT ? *current != 0 : current != loaded[i])) return 9;
        if (strcmp(before[i], defaults[i]) || strncmp(loaded[i], "entry-", 6)) return 10;
        printf("reload %u ", i+1);
        if (print_bytes(current, strlen(current))) return 11;
    }
    if (size_help_data != 10 || memcmp(help_data, "other\nhelp", 10)) return 12;
    lmsg_init(NULL);
    if (strcmp(lmsg(1), "second") || size_help_data <= 10) return 13;
    printf("count %u\n", (unsigned)COUNT);
    return 0;
}
