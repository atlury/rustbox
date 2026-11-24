"""Compare both public bridge monitors in a disposable Linux network namespace."""
# SPDX-License-Identifier: GPL-2.0-or-later

from contextlib import ExitStack
from pathlib import Path
import subprocess
import time

PROGRAMS = Path("/rustbox-iproute2/programs-gcc")
DEVICE = "rbtest"


def main():
    def ip(*args):
        subprocess.run([PROGRAMS / "ip", *args], check=True)

    def fdb(action, address):
        subprocess.run([PROGRAMS / "bridge", "fdb", action, address, "dev", DEVICE,
                        "self", "local", "vlan", "1"], check=True)

    ip("link", "add", DEVICE, "type", "bridge")
    with ExitStack() as cleanup:
        cleanup.callback(ip, "link", "del", DEVICE)
        ip("link", "set", DEVICE, "up")
        logs = []
        monitors = []
        for name, binary in [("canonical", PROGRAMS / "bridge"), ("candidate", "./bridge")]:
            output = Path(f"kernel-{name}.out")
            error = Path(f"kernel-{name}.err")
            proc = subprocess.Popen([binary, "monitor", "fdb"],
                                    stdout=cleanup.enter_context(output.open("wb")),
                                    stderr=cleanup.enter_context(error.open("wb")))
            monitors.append(proc)
            cleanup.callback(proc.wait)
            cleanup.callback(proc.kill)
            logs.append((output, error))

        # A printed marker confirms subscription and dispatch through the
        # printer. Later markers delimit the observations from both processes.
        def wait_for_marker(phase):
            for serial in range(1, 41):
                marker = f"02:00:00:11:{phase:02x}:{serial:02x}"
                fdb("add", marker)
                deadline = time.monotonic() + 0.25
                while time.monotonic() < deadline:
                    for proc, (_, error) in zip(monitors, logs):
                        if proc.poll() is not None:
                            raise RuntimeError(f"monitor exited ({proc.returncode}): {error.read_bytes()!r}")
                    if all(marker.encode() in output.read_bytes() for output, _ in logs):
                        return
                    time.sleep(0.02)
            raise RuntimeError("both monitors did not observe the FDB marker")

        wait_for_marker(1)
        target = "02:00:00:42:00:01"
        fdb("add", target)
        fdb("del", target)
        wait_for_marker(2)
        events = [[line for line in out.read_bytes().splitlines() if target.encode() in line]
                  for out, _ in logs]
        assert events[0] == events[1], events
        # Linux may emit both master and self notifications for the same update.
        added = [line for line in events[0] if not line.startswith(b"Deleted ")]
        deleted = [line.removeprefix(b"Deleted ") for line in events[0] if line.startswith(b"Deleted ")]
        assert added and sorted(added) == sorted(deleted), events
        assert events[0][:len(added)] == added, events
        for _, error in logs:
            assert error.read_bytes() == b"", error.read_bytes()
        print(f"Public monitors matched {len(added)} add and {len(deleted)} delete notifications.")


if __name__ == "__main__":
    main()
