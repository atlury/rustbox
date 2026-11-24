"""Offline saved records and live, local Netlink datagrams for the FDB pilot."""
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import re
import socket
import struct
import subprocess


def attr(kind, payload):
    size = 4 + len(payload)
    return struct.pack("=HH", size, kind) + payload + bytes(-size % 4)


def record(vlan, size=None, extra=b""):
    ndmsg = struct.pack("=BBHiHBB", 7, 0, 0, 0, 0x80, 0, 0)
    # Duplicate types exercise first-match selection after masking NLA_F_NESTED.
    body = ndmsg + attr(0x8005, struct.pack("=H", vlan)) + attr(5, struct.pack("=H", 99))
    body += extra
    if size is not None:
        # Ordinary unknown attribute, ignored by the FDB printer.
        body += attr(0x3fff, bytes(size - 16 - len(body) - 4))
        assert len(body) + 16 == size
    return struct.pack("=IHHII", len(body) + 16, 28, 0, 0, 0) + body


def receive(command, datagrams):
    with socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 2) as receiver, \
            socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 2) as sender:
        receiver.bind((0, 0))
        sender.bind((0, 0))
        sender.settimeout(5)
        for packet in datagrams:
            sent = sender.sendto(packet, receiver.getsockname())
            assert sent == len(packet)
        return subprocess.run(command, stdin=receiver, capture_output=True, timeout=45)


def check_nested(command):
    # Independently check the printed meanings, in addition to byte parity.
    # Include duplicate parents and children, both forms of the nested bit,
    # unknown types, and a full-size message whose nested attribute comes last.
    cases = []
    for value in range(256):
        child = attr(1 | ((value & 1) << 15), bytes([value]))
        children = attr(2, b"") + child + attr(1, bytes([value ^ 3]))
        parent = attr(14 | ((value & 2) << 14), children)
        cases.append((record(50, extra=parent + attr(14, attr(1, b"\x03"))), value))
    cases.append((record(50, extra=attr(14, b"")), 0))
    parent = attr(0x800e, attr(0x8001, b"\x03"))
    filler = attr(0x3fff, bytes(16384 - len(record(50)) - len(parent) - 4))
    cases.append((record(50, extra=filler + parent), 3))
    assert len(cases[-1][0]) == 16384
    # The entire rejected child header and its diagnostic field are backed.
    rejected = attr(1, b"\x01") + struct.pack("=HH", 3, 0)
    cases.append((record(50, extra=attr(14, rejected)), 1))
    Path("nested.dump").write_bytes(b"".join(msg for msg, _ in cases))
    args = ["-d", "monitor", "file", "nested.dump"]
    expected = subprocess.run(["/rustbox-iproute2/programs-gcc/bridge", *args],
                              capture_output=True, timeout=45, check=True)
    lines = expected.stdout.splitlines()
    assert len(lines) == len(cases) and expected.stderr == b"!!!Deficit 4, rta_len=3\n"
    for line, (_, value) in zip(lines, cases):
        assert (b"activity_notify" in line.split()) == bool(value & 1)
        assert (b"inactive" in line.split()) == bool(value & 2)
    candidate = subprocess.run(["valgrind", "--tool=memcheck", "--error-exitcode=88",
                                "--log-file=nested.memcheck", *command, *args],
                               capture_output=True, timeout=45)
    if candidate.returncode:
        raise RuntimeError(f"{candidate.stderr!r}\n{Path('nested.memcheck').read_text()}")
    assert (candidate.stdout, candidate.stderr) == (expected.stdout, expected.stderr)
    print(f"{len(cases)} nested activity records matched canonical bridge under Memcheck.")


def main():
    small = record(42)
    Path("fdb.dump").write_bytes(small + record(42, 16384) + small)
    Path("oversize.dump").write_bytes(record(42, 16388))

    check_nested(["./bridge"])

    # A full datagram with two records, followed by one with two more; then a
    # valid datagram whose last whole record exceeds the listener's iov limit.
    packets = [
        small + record(43, 16384 - len(small)),
        record(44) + record(45),
        record(46, 16384) + record(47),
        record(48) + struct.pack("=IHHII", 16, 3, 0, 0, 0),
    ]
    oracle = receive(["./live-oracle"], packets)
    oracle.check_returncode()
    assert re.findall(rb"\bvlan (\d+)\b", oracle.stdout) == [b"42", b"43", b"44", b"45", b"46", b"48"]
    assert oracle.stderr == b"Message truncated\n", oracle.stderr
    for prefix in ([], ["valgrind", "--tool=memcheck", "--error-exitcode=88", "--log-file=live.memcheck"],
                   ["valgrind", "--tool=callgrind", "--callgrind-out-file=live.trace", "--log-file=live.log"]):
        candidate = receive([*prefix, "./live-candidate"], packets)
        if candidate.returncode == 88:
            raise RuntimeError(Path("live.memcheck").read_text())
        candidate.check_returncode()
        assert candidate.stdout == oracle.stdout and candidate.stderr == oracle.stderr
    print("Live listener matched six ordered FDB records and one truncation diagnostic.")

    for sizes in ([1, 2, 3, 4, 32767, 32768], [32769, 32770], [32771, 32772]):
        packets = [bytes([0xa5]) * size for size in sizes]
        command = ["valgrind", "--tool=memcheck", "--error-exitcode=88", "--log-file=heap.memcheck",
                   "./heap-receive", *map(str, sizes)]
        result = receive(command, packets)
        if result.returncode:
            raise RuntimeError(f"heap receiver failed: {result.stderr!r}\n{Path('heap.memcheck').read_text()}")
    print("Heap receiver preserved 10 datagrams and initialized each aligned diagnostic suffix.")


if __name__ == "__main__":
    main()
