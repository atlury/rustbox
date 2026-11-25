/* SPDX-License-Identifier: curl */
#include <curl/curl.h>
#include <stdio.h>

static long report_mode(const void *data, void *context, int remains)
{
    const struct curl_fileinfo *file = data;
    (void)context;
    (void)remains;
    printf("entry %s %s %o %u\n", file->filename, file->strings.perm, (unsigned)file->perm,
           !!(file->flags & CURLFINFOFLAG_KNOWN_PERM));
    return CURL_CHUNK_BGN_FUNC_SKIP;
}

int main(int argc, char **argv)
{
    if (curl_global_init(CURL_GLOBAL_ALL)) return 1;
    for (int arg = 1; arg < argc; ++arg) {
        CURL *easy = curl_easy_init();
        if (!easy || curl_easy_setopt(easy, CURLOPT_URL, argv[arg]) ||
            curl_easy_setopt(easy, CURLOPT_NOPROXY, "*") ||
            curl_easy_setopt(easy, CURLOPT_TIMEOUT, 30L) ||
            curl_easy_setopt(easy, CURLOPT_WILDCARDMATCH, 1L) ||
            curl_easy_setopt(easy, CURLOPT_CHUNK_BGN_FUNCTION, report_mode)) return 1;
        printf("case %d\n", arg);
        CURLcode result = curl_easy_perform(easy);
        printf("status %d\n", (int)result);
        curl_easy_cleanup(easy);
    }
    curl_global_cleanup();
    return 0;
}
