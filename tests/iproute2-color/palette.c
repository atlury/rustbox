/* SPDX-License-Identifier: GPL-2.0-or-later */
#define _GNU_SOURCE 1
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linux/types.h>
#include "color.h"

int main(int argc, char **argv)
{
    static const char *const backgrounds[] = {
        NULL, "", "x", "0", "1;0", "0;7", "0;7;8", "4;6", "6;9", "4;15", "7;", "3;garbage",
    };
    if (argc != 3)
        return 2;
    int mode = atoi(argv[1]);
    int json = atoi(argv[2]);
    for (size_t i = 0; i < sizeof backgrounds / sizeof backgrounds[0]; ++i) {
        if (backgrounds[i] ? setenv("COLORFGBG", backgrounds[i], 1) : unsetenv("COLORFGBG"))
            return 3;
        if (i % 2 ? setenv("NO_COLOR", i % 3 ? "1" : "", 1) : unsetenv("NO_COLOR"))
            return 4;
        int default_mode = default_color_opt();
        bool enabled = check_enable_color(mode, json);
        for (int attr = COLOR_IFNAME; attr <= COLOR_NONE; ++attr) {
            char *text = NULL;
            size_t length = 0;
            FILE *fp = open_memstream(&text, &length);
            if (!fp)
                return 5;
            int empty = color_fprintf(fp, attr, NULL);
            int printed = color_fprintf(fp, attr, "%*.*s/%02x", 5, 3, "abcdef", 32 + attr);
            if (fclose(fp) || empty != 0 || printed < 0 || (size_t)printed != length)
                return 6;
            printf("%zu %d %d %d %d %zu ", i, attr, default_mode, enabled, printed, length);
            if (fwrite(text, 1, length, stdout) != length || putchar('\n') == EOF)
                return 7;
            free(text);
        }
    }
    return ferror(stdout) ? 8 : 0;
}
