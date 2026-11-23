#!/usr/bin/env python3
"""Generate a C unit embedding Bison's required C/C++ runtime data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HELPERS = r'''
static char *rustbox_bison_active_dir;

static int
write_all(int fd, const unsigned char *data, size_t size)
{
  while (size) {
    ssize_t written = write(fd, data, size);
    if (written < 0) {
      if (errno == EINTR)
        continue;
      return -1;
    }
    if (written == 0) {
      errno = EIO;
      return -1;
    }
    data += written;
    size -= (size_t) written;
  }
  return 0;
}

static char *
join_path(const char *directory, const char *name)
{
  size_t left = strlen(directory), right = strlen(name);
  char *path;
  if (left > (size_t) -1 - right - 2)
    return NULL;
  path = malloc(left + right + 2);
  if (path != NULL)
    sprintf(path, "%s/%s", directory, name);
  return path;
}

static void
remove_resources(const char *directory)
{
  size_t i;
  char *path;
  if (directory == NULL)
    return;
  for (i = 0; i < sizeof rustbox_bison_resources / sizeof *rustbox_bison_resources; ++i) {
    path = join_path(directory, rustbox_bison_resources[i].name);
    if (path != NULL) {
      unlink(path);
      free(path);
    }
  }
  path = join_path(directory, "m4");
  if (path != NULL) {
    unlink(path);
    free(path);
  }
  path = join_path(directory, "skeletons");
  if (path != NULL) {
    rmdir(path);
    free(path);
  }
  path = join_path(directory, "m4sugar");
  if (path != NULL) {
    rmdir(path);
    free(path);
  }
  path = join_path(directory, "xslt");
  if (path != NULL) {
    rmdir(path);
    free(path);
  }
  rmdir(directory);
}

static void
cleanup_at_exit(void)
{
  remove_resources(rustbox_bison_active_dir);
  free(rustbox_bison_active_dir);
  rustbox_bison_active_dir = NULL;
}

int
rustbox_bison_resources_create(char **result)
{
  char template[] = "/tmp/rustbox-bison.XXXXXX";
  char *directory, *path;
  size_t i;
  int fd, failed;
  if (result == NULL || rustbox_bison_active_dir != NULL) {
    errno = EINVAL;
    return -1;
  }
  directory = mkdtemp(template);
  if (directory == NULL)
    return -1;
  rustbox_bison_active_dir = strdup(directory);
  if (rustbox_bison_active_dir == NULL)
    goto fail;
  path = join_path(directory, "skeletons");
  if (path == NULL || mkdir(path, 0700) != 0) {
    free(path);
    goto fail;
  }
  free(path);
  path = join_path(directory, "m4sugar");
  if (path == NULL || mkdir(path, 0700) != 0) {
    free(path);
    goto fail;
  }
  free(path);
  path = join_path(directory, "xslt");
  if (path == NULL || mkdir(path, 0700) != 0) {
    free(path);
    goto fail;
  }
  free(path);
  for (i = 0; i < sizeof rustbox_bison_resources / sizeof *rustbox_bison_resources; ++i) {
    path = join_path(directory, rustbox_bison_resources[i].name);
    if (path == NULL)
      goto fail;
    fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    free(path);
    if (fd < 0)
      goto fail;
    failed = write_all(fd, rustbox_bison_resources[i].data,
                       rustbox_bison_resources[i].size);
    if (close(fd) != 0)
      failed = -1;
    if (failed != 0)
      goto fail;
  }
  path = join_path(directory, "m4");
  if (path == NULL || symlink("/proc/self/exe", path) != 0) {
    free(path);
    goto fail;
  }
  free(path);
  if (atexit(cleanup_at_exit) != 0)
    goto fail;
  *result = strdup(directory);
  if (*result == NULL)
    goto fail;
  return 0;
fail:
  {
    int saved = errno;
    cleanup_at_exit();
    errno = saved;
  }
  return -1;
}

void
rustbox_bison_resources_remove(char *directory)
{
  if (directory == NULL)
    return;
  if (rustbox_bison_active_dir != NULL
      && strcmp(directory, rustbox_bison_active_dir) == 0)
    cleanup_at_exit();
  else
    remove_resources(directory);
  free(directory);
}

static int
verify_persistent_resources(const char *directory)
{
  struct stat status;
  char *path;
  unsigned char buffer[4096];
  size_t i, offset;
  ssize_t amount;
  int fd;
  if (lstat(directory, &status) != 0 || !S_ISDIR(status.st_mode)
      || status.st_uid != geteuid() || (status.st_mode & 077) != 0) {
    errno = EACCES;
    return -1;
  }
  for (i = 0; i < sizeof rustbox_bison_resources / sizeof *rustbox_bison_resources; ++i) {
    path = join_path(directory, rustbox_bison_resources[i].name);
    if (path == NULL)
      return -1;
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    free(path);
    if (fd < 0 || fstat(fd, &status) != 0 || !S_ISREG(status.st_mode)
        || (size_t) status.st_size != rustbox_bison_resources[i].size) {
      if (fd >= 0)
        close(fd);
      errno = EIO;
      return -1;
    }
    offset = 0;
    while (offset < rustbox_bison_resources[i].size) {
      size_t wanted = rustbox_bison_resources[i].size - offset;
      if (wanted > sizeof buffer)
        wanted = sizeof buffer;
      amount = read(fd, buffer, wanted);
      if (amount <= 0
          || memcmp(buffer, rustbox_bison_resources[i].data + offset,
                    (size_t) amount) != 0) {
        close(fd);
        errno = EIO;
        return -1;
      }
      offset += (size_t) amount;
    }
    if (close(fd) != 0)
      return -1;
  }
  path = join_path(directory, "m4");
  if (path == NULL)
    return -1;
  amount = readlink(path, (char *) buffer, sizeof buffer);
  free(path);
  if (amount != (ssize_t) (sizeof "/proc/self/exe" - 1)
      || memcmp(buffer, "/proc/self/exe", sizeof "/proc/self/exe" - 1) != 0) {
    errno = EIO;
    return -1;
  }
  return 0;
}

int
rustbox_bison_resources_create_persistent(char **result)
{
  char *temporary = NULL;
  char persistent[160];
  int length, saved;
  if (result == NULL) {
    errno = EINVAL;
    return -1;
  }
  length = snprintf(persistent, sizeof persistent,
                    "/tmp/rustbox-bison-3.8.2-%lu-%s",
                    (unsigned long) geteuid(), RUSTBOX_BISON_RESOURCE_TAG);
  if (length < 0 || (size_t) length >= sizeof persistent) {
    errno = ENAMETOOLONG;
    return -1;
  }
  if (rustbox_bison_resources_create(&temporary) != 0)
    return -1;
  if (rename(temporary, persistent) == 0) {
    free(rustbox_bison_active_dir);
    rustbox_bison_active_dir = NULL;
    free(temporary);
  } else if (errno == EEXIST || errno == ENOTEMPTY) {
    rustbox_bison_resources_remove(temporary);
  } else {
    saved = errno;
    rustbox_bison_resources_remove(temporary);
    errno = saved;
    return -1;
  }
  if (verify_persistent_resources(persistent) != 0)
    return -1;
  *result = strdup(persistent);
  return *result == NULL ? -1 : 0;
}
'''


def c_bytes(data: bytes) -> str:
    rows = []
    for offset in range(0, len(data), 16):
        rows.append("  " + ", ".join(
            f"0x{byte:02x}" for byte in data[offset:offset + 16]
        ))
    return ",\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datadir", required=True, type=Path)
    parser.add_argument("--oracle-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    datadir = args.datadir.resolve()
    oracle = json.loads(args.oracle_evidence.read_text())
    prefix = "/usr/share/bison/"
    names = []
    for absolute in oracle["required_c_cxx_runtime_resources"]:
        if not absolute.startswith(prefix):
            raise RuntimeError(f"Bison resource escapes datadir: {absolute}")
        names.append(absolute.removeprefix(prefix))
    supplemental = [
        "bison-default.css",
        "xslt/bison.xsl",
        "xslt/xml2dot.xsl",
        "xslt/xml2text.xsl",
        "xslt/xml2xhtml.xsl",
    ]
    installed = set(oracle["installed_files"])
    if any(prefix + name not in installed for name in supplemental):
        raise RuntimeError("Bison report resource closure changed")
    names.extend(supplemental)
    if len(names) != 22 or len(set(names)) != 22:
        raise RuntimeError("Bison embedded resource closure changed")
    if any(
        Path(name).is_absolute() or ".." in Path(name).parts
        or Path(name).parent.as_posix() not in (".", "skeletons", "m4sugar", "xslt")
        for name in names
    ):
        raise RuntimeError("Bison embedded resource has an unsafe path")

    records, declarations, table = [], [], []
    for index, name in enumerate(names):
        path = datadir / name
        data = path.read_bytes()
        symbol = f"rustbox_bison_resource_{index:02d}"
        declarations.append(
            f"static const unsigned char {symbol}[] = {{\n{c_bytes(data)}\n}};\n"
        )
        table.append(f'  {{"{name}", {symbol}, sizeof {symbol}}}')
        records.append({
            "name": name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })

    resource_tag = hashlib.sha256(b"".join(
        (name.encode() + b"\0" + (datadir / name).read_bytes()) for name in names
    )).hexdigest()[:24]
    source = """/* Generated by generate_bison_resources.py. */
#define _GNU_SOURCE 1
#define RUSTBOX_BISON_RESOURCE_TAG "@RESOURCE_TAG@"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

struct rustbox_bison_resource {
  const char *name;
  const unsigned char *data;
  size_t size;
};

""".replace("@RESOURCE_TAG@", resource_tag) + "\n".join(declarations) + (
        "\nstatic const struct rustbox_bison_resource rustbox_bison_resources[] = {\n"
        + ",\n".join(table) + "\n};\n\n" + HELPERS
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source)
    manifest = {
        "schema": 1,
        "resources": records,
        "resources_count": len(records),
        "resources_bytes": sum(record["bytes"] for record in records),
        "generated_c_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "m4_route": "/proc/self/exe through a private m4 symlink",
        "persistent_resource_tag": resource_tag,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "resources": len(records), "bytes": manifest["resources_bytes"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
