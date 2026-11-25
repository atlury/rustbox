/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <limits.h>
#include <linux/types.h>
#include <stdio.h>
#include <string.h>
#include "rt_names.h"

extern int numeric;

static void forward(int dscp, int id, int capacity)
{
    char storage[24];
    memset(storage, 'Z', sizeof storage);
    storage[sizeof storage - 1] = 0;
    char *buffer = storage + 1;
    errno = EDOM;
    const char *name = dscp ? rtnl_dscp_n2a(id, buffer, capacity)
                            : rtnl_dsfield_n2a(id, buffer, capacity);
    int error = errno;
    printf("F %d %d %d %d %d %d ", dscp, numeric, id, capacity, name == buffer, error);
    for (size_t i = 0; i < sizeof storage; ++i)
        printf("%02x", (unsigned char)storage[i]);
    printf(" %s\n", name);
}

static void reverse(int dscp, const char *query)
{
    __u32 id = 0xfacebeef;
    errno = EDOM;
    int status = dscp ? rtnl_dscp_a2n(&id, query) : rtnl_dsfield_a2n(&id, query);
    int error = errno;
    printf("R %d %s %d %u %d\n", dscp, query, status, id, error);
}

int main(void)
{
    const char *initial = rtnl_dsfield_get_name(0);
    printf("first %s\n", initial);
    numeric = 1;
    forward(0, 127, 8);
    forward(1, 12, 8);
    numeric = 0;
    for (int id = -1; id <= 256; ++id) {
        errno = EDOM;
        const char *name = rtnl_dsfield_get_name(id);
        int error = errno;
        printf("N %d %d %s\n", id, error, name ? name : "(null)");
    }
    const char *loaded = rtnl_dsfield_get_name(0);
    printf("loaded %s retained %s identical %d\n", loaded, initial, loaded == initial);
    for (numeric = 0; numeric < 2; ++numeric) {
        for (int cap = 0; cap <= 12; cap += 2) {
            for (int id = -1; id <= 256; ++id)
                forward(0, id, cap);
            forward(0, INT_MIN, cap);
            forward(0, INT_MAX, cap);
            for (int id = 0; id <= 64; ++id)
                forward(1, id, cap);
        }
    }
    numeric = 0;
    const char *queries[] = {"", "0", "0x10", "10", "010", "ff", "100", "256",
        "+17", "-1", "2tail", " 10", "17 ", "184467440737095516160",
        "vendor", "local", "first", "dup", "raw-\xff", "bogus"};
    for (size_t i = 0; i < sizeof queries / sizeof *queries; ++i) {
        for (int dscp = 0; dscp < 2; ++dscp) {
            reverse(dscp, "dup");
            reverse(dscp, queries[i]);
            reverse(dscp, "dup");
        }
    }
    for (unsigned i = 0; i <= 256; ++i) {
        char hex[16];
        snprintf(hex, sizeof hex, "%x", i);
        reverse(0, hex);
        reverse(1, hex);
    }
    return 0;
}
