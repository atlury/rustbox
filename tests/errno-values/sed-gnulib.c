/* SPDX-License-Identifier: 0BSD */
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct quoting_options;
extern size_t quotearg_buffer(char *, size_t, const char *, size_t, const struct quoting_options *);
extern void *rpl_reallocarray(void *, size_t, size_t);

int main(void)
{
    const int saved[] = {INT_MIN, -1, 0, EAGAIN, INT_MAX};
    const char input[] = {'A', '\0', '\'', '\n', (char)0xff, 'Z'};
    for (size_t i = 0; i < sizeof saved / sizeof *saved; ++i) {
        for (size_t cap = 0; cap <= 14; ++cap) {
            char output[16];
            memset(output, 0x55, sizeof output);
            errno = saved[i];
            size_t written = quotearg_buffer(output, cap, input, sizeof input, NULL);
            int observed = errno;
            if (observed != saved[i] || output[cap] != 0x55)
                return 1;
            printf("%zu %zu %zu %d ", i, cap, written, observed);
            if (fwrite(output, 1, sizeof output, stdout) != sizeof output || putchar('\n') == EOF)
                return 2;
        }
        unsigned char *old = malloc(1);
        if (!old)
            return 3;
        *old = 42;
        errno = saved[i];
        void *result = rpl_reallocarray(old, SIZE_MAX, 2);
        if (result || errno != ENOMEM || *old != 42)
            return 4;
        free(old);
    }
    return ferror(stdout);
}
