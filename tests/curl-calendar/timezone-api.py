#!/usr/bin/env python3
"""Compare canonical curl_getdate and the selected archive on named time zones."""
# SPDX-License-Identifier: curl
import argparse
from datetime import datetime, timezone
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from test_curl_month_pilot import compare


def cases():
    stamp = int(datetime(2001, 1, 5, 13, 14, 15, tzinfo=timezone.utc).timestamp())
    known = {b"A": -3600, b"I": -9 * 3600, b"K": -10 * 3600, b"M": -12 * 3600,
             b"N": 3600, b"Y": 12 * 3600, b"Z": 0, b"UT": 0, b"NT": 11 * 3600,
             b"GMT": 0, b"BST": -3600, b"EDT": 4 * 3600, b"IDLE": -12 * 3600,
             b"IDLW": 12 * 3600, b"NZDT": -13 * 3600}
    words = list(known)
    expected = [stamp + seconds for seconds in known.values()]
    zones = (b"A B C D E F G H I J K L M N O P Q R S T U V W X Y Z NT UT "
             b"ADT AST BST CAT CCT CDT CET CST EDT EET EST FST FWT GMT GST HDT HST JST MDT MET MST NZT "
             b"PDT PST UTC WAT WET YDT YST AHST CEST EADT EAST IDLE IDLW MEST MESZ MEWT NZDT NZST WADT WAST")
    mutations = {b"", b"GMT+0000", b"+0530", b"-0630", b"A" * 12, b"A" * 13, b"\xffGMT"}
    for zone in zones.split():
        mutations.update(bytes(letters) for letters in product(*[(c, c + 32) for c in zone]))
        for i in range(len(zone)):
            for c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZ\x80\xff":
                mutations.add(zone[:i] + bytes([c]) + zone[i+1:])
    words.extend(sorted(mutations.difference(words)))
    data = b"".join(b"Fri, 05 Jan 2001 13:14:15 " + word + b"\n" for word in words)
    return data, expected, len(words)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pilot", type=Path)
    p.add_argument("link", type=Path)
    args = p.parse_args()
    print(json.dumps(compare(args.pilot, args.link, cases), indent=2, sort_keys=True))
