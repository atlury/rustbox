/* SPDX-License-Identifier: LGPL-2.0-only */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

extern int ext2fs_set_bit(unsigned int, void *);
extern int ext2fs_clear_bit(unsigned int, void *);
extern int ext2fs_test_bit(unsigned int, const void *);
extern int ext2fs_set_bit64(uint64_t, void *);
extern int ext2fs_clear_bit64(uint64_t, void *);
extern int ext2fs_test_bit64(uint64_t, const void *);

enum op { SET, CLEAR, TEST };
static uint64_t calls;

static void check(unsigned char *base, uint64_t nr, int wide, enum op op)
{
    unsigned char *byte = base + (nr / 8);
    unsigned int before = *byte, mask = 1U << (nr % 8);
    int got;
    if (!wide && nr > UINT32_MAX)
        abort();
    errno = EDOM;
    if (wide) {
        got = op == SET ? ext2fs_set_bit64(nr, base)
            : op == CLEAR ? ext2fs_clear_bit64(nr, base) : ext2fs_test_bit64(nr, base);
    } else {
        unsigned int n = (unsigned int) nr;
        got = op == SET ? ext2fs_set_bit(n, base)
            : op == CLEAR ? ext2fs_clear_bit(n, base) : ext2fs_test_bit(n, base);
    }
    if (got != (int) (before & mask) || errno != EDOM ||
        *byte != (op == SET ? before | mask : op == CLEAR ? before & ~mask : before))
        abort();
    calls++;
}

static void exhaust(void)
{
    unsigned char data[35], expected[sizeof data];
    for (int wide = 0; wide < 2; wide++)
        for (int op = SET; op <= TEST; op++)
            for (unsigned int value = 0; value < 256; value++)
                for (unsigned int bit = 0; bit < 8; bit++)
                    for (unsigned int i = 0; i < 32; i++) {
                        memset(data, 0xa5, sizeof data);
                        data[1+i] = (unsigned char) value;
                        memcpy(expected, data, sizeof data);
                        check(data+1, 8*i+bit, wide, (enum op) op);
                        expected[1+i] = data[1+i];
                        if (memcmp(expected, data, sizeof data))
                            abort();
                    }
}

static void boundaries(void)
{
    size_t page = (size_t) sysconf(_SC_PAGESIZE);
    /* Reserve address space; only the first, last and 2^32-bit boundary pages are touched. */
    size_t edge = ((size_t) UINT32_MAX / 8 + 1);
    size_t length = edge + 3 * page;
    unsigned char *mapping = mmap(NULL, length, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (mapping == MAP_FAILED)
        abort();
    unsigned char *base = mapping + page;
    if (mprotect(base, page, PROT_READ | PROT_WRITE) ||
        mprotect(base + edge - page, 2*page, PROT_READ | PROT_WRITE))
        abort();
    uint64_t positions[] = {0, 7, 8, page*8-1, UINT32_MAX-7, UINT32_MAX,
                            (uint64_t) UINT32_MAX+1, (uint64_t) (edge+page)*8-1};
    for (size_t i = 0; i < sizeof positions/sizeof *positions; i++)
        for (int wide = (positions[i] > UINT32_MAX); wide <= 1; wide++) {
            check(base, positions[i], wide, SET);
            check(base, positions[i], wide, TEST);
            check(base, positions[i], wide, CLEAR);
        }
    if (mprotect(base, page, PROT_READ))
        abort();
    check(base, 0, 0, TEST);
    check(base, 7, 1, TEST);
    if (munmap(mapping, length))
        abort();
}

int main(void)
{
    exhaust();
    boundaries();
    printf("%" PRIu64 " bitmap calls passed\n", calls);
    return 0;
}
