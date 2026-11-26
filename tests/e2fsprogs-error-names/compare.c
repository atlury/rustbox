/* SPDX-License-Identifier: 0BSD */
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern const char *e2p_errcode2str(unsigned int);

int main(void)
{
    static const unsigned int edges[] = {18, 19, 99, 100, 999, 1000, INT_MAX, INT_MAX + 1U, UINT_MAX};
    const char *known[18];
    const char *fallback = e2p_errcode2str(UINT_MAX);
    uint32_t state = 1;
    if (!fallback)
        return 1;
    for (unsigned int i = 0; i < 18; ++i) {
        errno = ERANGE;
        known[i] = e2p_errcode2str(i);
        if (!known[i] || known[i] == fallback || errno != ERANGE)
            return 2;
        puts(known[i]);
    }
    for (unsigned int i = 0; i < 4096; ++i) {
        state = state * UINT32_C(1664525) + UINT32_C(1013904223);
        unsigned int code = i < sizeof(edges) / sizeof(edges[0]) ? edges[i] : state;
        if (code < 18)
            code += 18;
        char expected[32];
        snprintf(expected, sizeof(expected), "UNKNOWN_ERRCODE_%u", code);
        errno = ERANGE;
        const char *text = e2p_errcode2str(code);
        if (errno != ERANGE || text != fallback || strcmp(fallback, expected))
            return 3;
        if (known[i % 18] != e2p_errcode2str(i % 18) || strcmp(fallback, expected))
            return 4;
        puts(text);
    }
    for (unsigned int i = 0; i < 18; ++i)
        puts(known[i]);
    return ferror(stdout) ? 5 : 0;
}
