/* SPDX-License-Identifier: GPL-2.0-only */
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

extern unsigned ext2fs_bitcount(const void *, unsigned);
extern unsigned rustbox_e2fsprogs_bitcount(const void *, unsigned);
static unsigned cases;

static unsigned compare(const void *data, unsigned len)
{
    unsigned expected = ext2fs_bitcount(data, len);
    unsigned actual = rustbox_e2fsprogs_bitcount(data, len);
    if (actual != expected) {
        fprintf(stderr, "length %u: expected %u, got %u\n", len, expected, actual);
        exit(1);
    }
    ++cases;
    return actual;
}

int main(void)
{
    unsigned char bytes[4096 + 32];
    uint32_t state = 42;
    for (unsigned i = 0; i < sizeof bytes; ++i) {
        state = state * UINT32_C(1664525) + UINT32_C(1013904223);
        bytes[i] = state >> 24;
    }
    compare(NULL, 0);
    for (unsigned offset = 0; offset < 32; ++offset) {
        for (unsigned len = 0; len <= 256; ++len)
            compare(bytes + offset, len);
        compare(bytes + offset, 4096);
    }

    /* No reads outside the caller's extent, even at either page boundary. */
    long page = sysconf(_SC_PAGESIZE);
    if (page <= 0 || page > INT_MAX / 3)
        return 1;
    unsigned char *mapping = mmap(NULL, 3 * page, PROT_NONE,
                                  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mapping == MAP_FAILED || mprotect(mapping + page, page, PROT_READ | PROT_WRITE))
        return 1;
    for (long i = 0; i < page; ++i)
        mapping[page + i] = (unsigned char)i;
    for (unsigned len = 0; len <= (unsigned)page; ++len) {
        compare(mapping + page, len);
        compare(mapping + 2 * page - len, len);
    }
    if (munmap(mapping, 3 * page))
        return 1;

    /* An all-ones bitmap one byte beyond the unsigned accumulator boundary. */
    unsigned length = UINT_MAX / 8u + 2u;
    unsigned char *ones = malloc(length);
    if (!ones)
        return 1;
    memset(ones, 0xff, length);
    unsigned wrapped = compare(ones, length);
    free(ones);
    if (wrapped != 8)
        return 1;
    printf("%u canonical bitmap count comparisons passed, including uint32 wraparound\n", cases);
    return 0;
}
