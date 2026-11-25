/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <linux/types.h>
#include "rt_names.h"

extern int numeric;

static void forward(int id, int size)
{
    char storage[32];
    memset(storage, 'Z', sizeof(storage));
    storage[sizeof(storage) - 1] = 0;
    errno = EDOM;
    const char *value = nl_proto_n2a(id, storage + 1, size);
    int saved = errno;
    printf("F %d %d %d %d %d ", numeric, id, size, value == storage + 1, saved);
    for (size_t i = 0; i < sizeof(storage); i++)
        printf("%02x", (unsigned char)storage[i]);
    printf(" %s\n", value);
}

static void reverse(const char *name)
{
    __u32 id = 0xfedcba98u;
    errno = EDOM;
    int status = nl_proto_a2n(&id, name);
    int saved = errno;
    printf("R %s %d %u %d\n", name, status, id, saved);
}

int main(void)
{
    numeric = 1;
    forward(0, 16);
    numeric = 0;
    forward(-1, 16);
    forward(256, 16);
    char buf[32];
    const char *first = nl_proto_n2a(0, buf, sizeof(buf));
    printf("first %s\n", first);
    for (int mode = 0; mode < 2; mode++) {
        numeric = mode;
        for (int id = -1; id <= 256; id++)
            for (int size = 0; size <= 18; size += 2)
                forward(id, size);
        forward(INT_MIN, 18);
        forward(INT_MAX, 18);
    }
    numeric = 0;
    for (int id = 0; id <= 255; id++)
        reverse(nl_proto_n2a(id, buf, sizeof(buf)));
    const char *queries[] = {"", "rtnl", "local", "vendor", "duplicate", "raw-\xff",
        "0x10", "011", "255", "256", "-1", "+17", "14tail", "184467440737095516160"};
    for (size_t i = 0; i < sizeof(queries)/sizeof(*queries); i++) {
        reverse(first);
        reverse(queries[i]);
        reverse(first);
    }
    printf("retained %s %d\n", first, first == nl_proto_n2a(0, buf, sizeof(buf)));
    return 0;
}
