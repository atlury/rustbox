/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include "rt_names.h"

extern int numeric;

static void forward(int id, int capacity)
{
    char area[24];
    memset(area, 'Z', sizeof area);
    area[sizeof area - 1] = 0;
    errno = EDOM;
    const char *value = rtnl_group_n2a(id, area + 1, capacity);
    int err = errno;
    printf("F %d %d %d %d %d ", numeric, id, capacity, value == area + 1, err);
    for (size_t i = 0; i < sizeof area; i++)
        printf("%02x", (unsigned char)area[i]);
    printf(" %s\n", value);
}

static void reverse(const char *key)
{
    int id = -913;
    errno = EDOM;
    int status = rtnl_group_a2n(&id, key);
    int err = errno;
    printf("R %s %d %d %d\n", key, status, id, err);
}

int main(void)
{
    char buf[24];
    errno = EDOM;
    const char *retained = rtnl_group_n2a(0, buf, sizeof buf);
    int init_errno = errno;
    printf("first %s %d\n", retained, init_errno);
    for (numeric = 0; numeric <= 1; numeric++) {
        for (int id = -2; id <= 1026; id++)
            for (int cap = 0; cap <= 2; cap++)
                forward(id, cap);
        forward(INT_MIN, 16);
        forward(INT_MAX, 16);
    }
    numeric = 0;
    const char *keys[] = {"default", "vendor", "local", "dup", "samebucket", "renamed", "first", "ignored",
                          "raw-\377", "", " ", "0x101", "0", "010", "+10", " 8", "8 ", "08", "0x10x",
                          "-1", "-4294967296", "2147483647", "2147483648", "4294967296",
                          "4294967297", "9223372036854775808", "-9223372036854775809", "dup", "default"};
    for (size_t i = 0; i < sizeof keys / sizeof keys[0]; i++)
        reverse(keys[i]);
    const char *again = rtnl_group_n2a(0, buf, sizeof buf);
    printf("retained %s %d\n", retained, again == retained);
    return 0;
}
