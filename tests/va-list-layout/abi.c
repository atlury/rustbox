// SPDX-License-Identifier: 0BSD
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef __typeof__((*(va_list *)0)[0]) va_tag;
extern size_t rust_layout(unsigned field);
extern uintptr_t rust_field(const va_tag *tag, unsigned field);

static unsigned observations;
static int check_cursor(va_list cursor) {
    uintptr_t expected[] = {cursor->gp_offset, cursor->fp_offset,
                            (uintptr_t)cursor->overflow_arg_area, (uintptr_t)cursor->reg_save_area};
    for (unsigned i = 0; i < 4; ++i)
        if (rust_field(cursor, i) != expected[i]) return 0;
    ++observations;
    return 1;
}

static void consume(unsigned pairs, ...) {
    va_list cursor, saved;
    va_start(cursor, pairs);
    va_copy(saved, cursor);
    for (unsigned pass = 0; pass < 2; ++pass) {
        for (unsigned n = 1; n <= pairs; ++n) {
            if (pass == 0) {
                if (!check_cursor(cursor) || va_arg(cursor, int) != (int)n ||
                    !check_cursor(cursor) || va_arg(cursor, double) != n + 0.5) abort();
            } else {
                if (!check_cursor(saved) || va_arg(saved, int) != (int)n ||
                    !check_cursor(saved) || va_arg(saved, double) != n + 0.5) abort();
            }
        }
    }
    va_end(saved);
    va_end(cursor);
}

int main(void) {
    size_t layout[] = {sizeof(va_tag), _Alignof(va_tag), offsetof(va_tag, gp_offset),
                       offsetof(va_tag, fp_offset), offsetof(va_tag, overflow_arg_area),
                       offsetof(va_tag, reg_save_area)};
    for (unsigned i = 0; i < 6; ++i)
        if (rust_layout(i) != layout[i]) return 1;
    consume(10, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 10.5);
    printf("%zu %zu %zu %zu %zu %zu %u\n", layout[0], layout[1], layout[2], layout[3],
           layout[4], layout[5], observations);
    return 0;
}
