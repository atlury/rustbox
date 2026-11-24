/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "libnetlink.h"

/* Layout assumptions used by the top-level FDB replay bound test. */
_Static_assert(NLMSG_LENGTH(sizeof(struct ndmsg)) == 28, "FDB attribute offset");
_Static_assert(NLMSG_ALIGNTO == 4 && RTA_ALIGNTO == 4, "record alignment");
_Static_assert(sizeof(((struct rtattr *)0)->rta_len) == 2, "diagnostic field");

enum { slots = 16, words = 20 };
static unsigned cases;

static void check_wide(unsigned length)
{
    unsigned stride = RTA_ALIGN(length);
    unsigned char *buffer = malloc(stride + sizeof(struct rtattr));
    struct rtattr **table = malloc((UINT16_MAX + 1UL) * sizeof(*table));
    if (!buffer || !table)
        abort();
    struct rtattr *first = (void *)buffer;
    struct rtattr *last = (void *)(buffer + stride);
    *first = (struct rtattr){ .rta_len = length, .rta_type = UINT16_MAX };
    *last = (struct rtattr){ .rta_len = sizeof(*last), .rta_type = 0 };
    /* Output slots, payload and padding are deliberately uninitialized. */
    if (parse_rtattr_flags(table, UINT16_MAX, first, stride + sizeof(*last), 0))
        abort();
    if (table[UINT16_MAX] != first || table[0] != last)
        abort();
    for (unsigned i = 1; i < UINT16_MAX; ++i)
        if (table[i])
            abort();
    printf("%u wide %u\n", ++cases, length);
    free(table);
    free(buffer);
}

static void check(struct rtattr *input, int len, int max, unsigned short mask)
{
    struct rtattr *table[slots + 2];
    struct rtattr before[words];
    struct rtattr sentinel;
    for (int i = 0; i < slots + 2; ++i)
        table[i] = &sentinel;
    if (input)
        memcpy(before, input, sizeof(before));
    fprintf(stderr, "#%u\n", ++cases);
    errno = EDOM;
    int rc = parse_rtattr_flags(table + 1, max, input, len, mask);
    int saved_errno = errno;
    if (table[0] != &sentinel || (input && memcmp(input, before, sizeof(before))))
        abort();
    printf("%u %d %d", cases, rc, saved_errno);
    for (int i = 0; i <= max; ++i) {
        int offset = -1;
        if (table[1+i]) {
            /* Verify membership by equality before doing any arithmetic. */
            for (int j = 0; j < words; ++j)
                if (table[1+i] == &input[j])
                    offset = j * sizeof(*input);
            if (offset < 0)
                abort();
        }
        printf(" %d", offset);
    }
    for (int i = max + 2; i < slots + 2; ++i)
        if (table[i] != &sentinel)
            abort();
    putchar('\n');
}

int main(void)
{
    /* Fully backed, aligned storage also covers upstream's deficit diagnostic. */
    struct rtattr input[words];
    static const unsigned short masks[] = {0, 0x4000, 0x8000, 0xc000, 0xffff};
    static const int maxima[] = {-1, 0, 3, slots - 1};
    check(NULL, 0, slots - 1, 0);
    check_wide(32767);
    check_wide(32768);
    check_wide(65534);
    check_wide(65535);
    for (unsigned length = 0; length <= 16; ++length) {
        for (int i = 0; i < words; ++i) {
            input[i].rta_len = 4;
            input[i].rta_type = (i % 3) | ((i % 4) << 14);
        }
        input[0].rta_len = length;
        for (int available = -1; available <= 40; ++available)
            for (unsigned m = 0; m < sizeof(masks)/sizeof(masks[0]); ++m)
                for (unsigned n = 0; n < sizeof(maxima)/sizeof(maxima[0]); ++n)
                    check(input, available, maxima[n], masks[m]);
    }
    printf("%u cases\n", cases);
    return 0;
}
