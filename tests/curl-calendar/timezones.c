/* SPDX-License-Identifier: curl */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

int checktz(const char *letters, size_t length);
int rustbox_test_timezone(uint8_t a, uint8_t b, uint8_t c, uint8_t d, size_t length);

static unsigned long cases, accepted;

static int visit(char word[5], size_t length)
{
    static const char alphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
    if (length) {
        int ref = checktz(word, length);
        int got = rustbox_test_timezone(word[0], word[1], word[2], word[3], length);
        if (ref != got) {
            fprintf(stderr, "%.*s: C %d, Rust %d\n", (int)length, word, ref, got);
            return 1;
        }
        ++cases;
        accepted += ref != -1;
    }
    if (length < 4) {
        for (size_t i = 0; i < sizeof alphabet - 1; ++i) {
            word[length] = alphabet[i];
            if (visit(word, length + 1))
                return 1;
        }
    }
    return 0;
}

int main(void)
{
    char word[5] = {0};
    if (visit(word, 0))
        return 1;
    printf("%lu tokens, %lu valid zones\n", cases, accepted);
    return 0;
}
