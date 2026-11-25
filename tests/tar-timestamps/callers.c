/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

int fdutimens(int, const char *, const struct timespec *);
int lutimens(const char *, const struct timespec *);

static void print_time(struct timespec value, time_t begin, time_t end) {
    if (value.tv_sec >= begin && value.tv_sec <= end)
        printf(" now");
    else
        printf(" %ld.%09ld", (long)value.tv_sec, value.tv_nsec);
}

int main(void) {
    const long nanos[] = {LONG_MIN, -1, 0, 1, 999999999, 1000000000,
                          UTIME_OMIT - 1, UTIME_OMIT, UTIME_NOW, UTIME_NOW + 1, LONG_MAX};
    const size_t count = sizeof(nanos) / sizeof(nanos[0]);
    const struct timespec initial[] = {{11, 123}, {13, 456}};
    int fd = open("file", O_CREAT | O_RDWR | O_EXCL, 0600);
    if (fd < 0 || symlink("file", "link")) return 1;
    for (int mode = 0; mode < 6; ++mode) {
        for (size_t n = 0; n <= count * count; ++n) {
            struct timespec pair[2] = {{41, nanos[n / count % count]}, {59, nanos[n % count]}};
            struct timespec original[2];
            memcpy(original, pair, sizeof(pair));
            const struct timespec *input = n == count * count ? NULL : pair;
            if (futimens(fd, initial) || utimensat(AT_FDCWD, "link", initial, AT_SYMLINK_NOFOLLOW)) return 2;
            time_t begin = time(NULL);
            errno = EDOM;
            int result;
            switch (mode) {
            case 0: result = fdutimens(fd, NULL, input); break;
            case 1: result = fdutimens(-1, "file", input); break;
            case 2: result = lutimens("link", input); break;
            case 3: result = fdutimens(-1, NULL, input); break;
            case 4: result = lutimens("absent", input); break;
            default: result = fdutimens(-1, "absent", input); break;
            }
            int error = errno;
            time_t end = time(NULL);
            struct stat file, link;
            if (fstat(fd, &file) || lstat("link", &link) || memcmp(pair, original, sizeof(pair))) return 3;
            printf("%d %zu %d %d", mode, n, result, error);
            print_time(file.st_atim, begin, end);
            print_time(file.st_mtim, begin, end);
            print_time(link.st_atim, begin, end);
            print_time(link.st_mtim, begin, end);
            puts("");
        }
    }
    return close(fd) != 0;
}
