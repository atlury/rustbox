/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <linux/types.h>
#include <stdio.h>
#include <string.h>
#include "rt_names.h"

extern int numeric;

static int write_config(const char *path, const char *line)
{
    FILE *file = fopen(path, "w");
    if (!file) return 1;
    int failed = fputs(line, file) == EOF;
    return fclose(file) == EOF || failed;
}

static int check_cache(const char *config)
{
    char buf[32];
    __u8 id = 177;
    numeric = 1;
    const char *number = rtnl_addrprot_n2a(199, buf, sizeof(buf));
    if (number != buf || strcmp(number, "0xc7") || write_config(config, "199 first\n")) return 1;
    numeric = 0;
    const char *name = rtnl_addrprot_n2a(199, buf, sizeof(buf));
    if (!name || name == buf || strcmp(name, "first") || write_config(config, "199 second\n")) return 1;
    if (name != rtnl_addrprot_n2a(199, buf, sizeof(buf)) || strcmp(name, "first")) return 1;
    if (rtnl_addrprot_a2n(&id, "first") || id != 199) return 1;
    if (rtnl_addrprot_a2n(&id, "second") != -1 || id != 199) return 1;
    puts("numeric lookup deferred configuration; the first named lookup retained its name and address");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "--cache") == 0) return check_cache(argv[2]);
    if (argc != 1) return 2;
    const char *inputs[] = {"unspec", "kernel_lo", "kernel_ra", "kernel_ll", "vendor", "local",
                            "vendor-only", "extra", "local-extra", "ignored", "duplicate", "raw-\xff",
                            "0", "011", "15", "0x10", "0xff", "256", "0x100", "-1", "", "unknown"};
    const int capacities[] = {0, 2, 32};
    // Numeric-only lookup precedes the first use of the lazy configuration.
    for (int mode = 1; mode >= 0; --mode) {
        numeric = mode;
        for (unsigned id = 0; id < 256; ++id) {
            for (size_t j = 0; j < sizeof(capacities)/sizeof(capacities[0]); ++j) {
                char storage[36];
                memset(storage, 0x5a, sizeof(storage));
                storage[34] = 0;
                char *buf = storage + 1;
                const char *name = rtnl_addrprot_n2a(id, buf, capacities[j]);
                if (!name) return 1;
                if (name != buf && name != rtnl_addrprot_n2a(id, buf, capacities[j])) return 1;
                printf("F %d %u %d %d ", mode, id, capacities[j], name == buf);
                for (size_t k = 0; k < sizeof(storage); ++k)
                    printf("%02x", (unsigned char)storage[k]);
                printf(" %s\n", name);
            }
        }
        for (size_t i = 0; i < sizeof(inputs)/sizeof(inputs[0]); ++i) {
            __u8 id = 177;
            int status = rtnl_addrprot_a2n(&id, inputs[i]);
            printf("R %d %s %d %u\n", mode, inputs[i], status, id);
        }
    }
    return 0;
}
