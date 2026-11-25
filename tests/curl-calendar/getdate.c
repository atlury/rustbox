/* SPDX-License-Identifier: curl */
#include <stdio.h>
#include <string.h>
#include <time.h>

extern time_t curl_getdate(const char *, const time_t *);

int main(void)
{
    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        line[strcspn(line, "\n")] = '\0';
        printf("%lld\n", (long long)curl_getdate(line, NULL));
    }
    return ferror(stdin) || ferror(stdout);
}
