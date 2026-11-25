/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <errno.h>
#include <limits.h>
#include <linux/types.h>
#include <stdio.h>
#include <string.h>
#include "rt_names.h"

extern int numeric;
struct table {
    const char *(*forward)(int, char *, int);
    int (*reverse)(__u32 *, const char *);
};
static const struct table tables[] = {
    {rtnl_rtscope_n2a, rtnl_rtscope_a2n},
    {rtnl_rtrealm_n2a, rtnl_rtrealm_a2n},
};

static void forward(int tab, int id, int cap)
{
    char bytes[32];
    memset(bytes, 'Z', sizeof(bytes));
    bytes[sizeof(bytes)-1] = 0;
    char *buf = bytes+1;
    errno = EDOM;
    const char *value = tables[tab].forward(id, buf, cap);
    int err = errno;
    printf("F %d %d %d %d %d %d ", tab, numeric, id, cap, value == buf, err);
    for (size_t i = 0; i < sizeof(bytes); ++i)
        printf("%02x", (unsigned char) bytes[i]);
    printf(" %s\n", value);
}

static void reverse(int tab, const char *name)
{
    __u32 id = 0xfedcba98u;
    errno = EDOM;
    int rc = tables[tab].reverse(&id, name);
    int err = errno;
    printf("R %d %s %d %u %d\n", tab, name, rc, id, err);
}

int main(void)
{
    const char *builtin[] = {"global", "unknown"};
    const char *queries[] = {"local", "vendor", "duplicate", "raw-\xff", "", "0", "0x10",
        "011", "255", "256", "-1", "+17", "14tail", "184467440737095516160", "missing"};
    char buf[32];
    const char *first[2];
    for (int t = 0; t < 2; ++t) {
        first[t] = tables[t].forward(0, buf, sizeof(buf));
        printf("initial %d %s\n", t, first[t]);
    }
    numeric = 1;
    for (int t = 0; t < 2; ++t)
        forward(t, 127, sizeof(buf)-2);
    numeric = 0;
    for (int t = 0; t < 2; ++t) {
        forward(t, 100, 16); /* First missing built-in loads the requested table. */
        const char *loaded = tables[t].forward(0, buf, sizeof(buf));
        printf("loaded %d %s retained %s identical %d\n", t, loaded, first[t], loaded == first[t]);
        for (int mode = 0; mode < 2; ++mode) {
            numeric = mode;
            for (int id = -1; id <= 256; ++id)
                for (int cap = 0; cap <= 18; cap += 2)
                    forward(t, id, cap);
            forward(t, INT_MIN, 18);
            forward(t, INT_MAX, 18);
        }
        numeric = 0;
    }
    for (size_t i = 0; i < sizeof(queries)/sizeof(*queries); ++i) {
        for (int t = 0; t < 2; ++t) {
            reverse(t, builtin[t]);
            reverse(t, queries[i]);
            reverse(t, builtin[t]);
            reverse(t, "duplicate");
            reverse(t, queries[i]);
            reverse(t, "duplicate");
        }
    }
    return 0;
}
