/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "rt_names.h"

extern int numeric;

static void forward(uint32_t id, int capacity)
{
    char area[32];
    memset(area, 'Z', sizeof area);
    area[sizeof area - 1] = 0;
    errno = EDOM;
    const char *value = rtnl_rttable_n2a(id, area + 1, capacity);
    int saved = errno;
    printf("F %d %u %d %d %d ", numeric, id, capacity, value == area + 1, saved);
    for (size_t i = 0; i < sizeof area; ++i)
        printf("%02x", (unsigned char)area[i]);
    printf(" %s\n", value);
}

static void reverse(const char *name)
{
    uint32_t id = 0xabcdef;
    errno = EDOM;
    int status = rtnl_rttable_a2n(&id, name);
    int saved = errno;
    printf("R %s %d %u %d\n", name, status, id, saved);
}

int main(int argc, char **argv)
{
    char buf[32];
    if (argc != 2)
        return 2;
    if (!strcmp(argv[1], "numeric")) {
        numeric = 1;
        forward(254, sizeof buf - 1);
    } else if (!strcmp(argv[1], "reverse")) {
        reverse("main");
    }
    numeric = 0;
    errno = EDOM;
    const char *retained = rtnl_rttable_n2a(254, buf, sizeof buf);
    int saved = errno;
    printf("first %s %d\n", retained, saved);
    for (numeric = 0; numeric < 2; ++numeric) {
        for (uint32_t id = 0; id <= 1025; ++id)
            for (int cap = 0; cap <= 3; ++cap)
                forward(id, cap);
        forward(INT32_MAX, 16);
        forward((uint32_t)INT32_MAX + 1, 16);
        forward(UINT32_MAX, 16);
    }
    const char *names[] = {"main","main","default","local","vendor","dup","renamed","raw-\377","shadow",
        "dangling","hidden","extra","upper","bad","part","after","directory","max","last","01","main",
        "","+10"," 5","5 ","0xFFFFFFFF","0x100000000","4294967295","4294967296","08","-1",
        "-18446744073709551615","18446744073709551616","dup","main"};
    for (size_t i = 0; i < sizeof names / sizeof names[0]; ++i)
        reverse(names[i]);
    numeric = 0;
    char next[32];
    const char *again = rtnl_rttable_n2a(254, next, sizeof next);
    printf("retained %s %d\n", retained, again == retained);
    return 0;
}
