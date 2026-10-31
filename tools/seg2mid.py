"""Extract MIDI events from a byte offset of the capture log into a .mid file.

Usage:
    python seg2mid.py <log> <offset_bytes> <out.mid> [title]
Prints: event count, duration, output size.
"""
import re
import sys

PACKET = re.compile(r"\[(\d+)\] RX ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2}) ([0-9A-F]{2})")
PPQ = 480
BPM = 120.0
TICKS_PER_MS = PPQ * (BPM / 60.0) / 1000.0


def varlen(n):
    if n < 0:
        n = 0
    buf = bytearray([n & 0x7F])
    n >>= 7
    while n:
        buf.append((n & 0x7F) | 0x80)
        n >>= 7
    buf.reverse()
    return bytes(buf)


def main():
    log, offset, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    title = sys.argv[4] if len(sys.argv) > 4 else "capture"

    events = []
    with open(log, "r", encoding="utf-8", errors="replace") as f:
        f.seek(offset)
        for line in f:
            m = PACKET.search(line)
            if not m:
                continue
            status = int(m.group(3), 16)
            high = status & 0xF0
            if high not in (0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0):
                continue
            events.append((int(m.group(1)), high, status & 0x0F,
                           int(m.group(4), 16), int(m.group(5), 16)))

    if not events:
        print("NO_EVENTS")
        raise SystemExit(2)

    track = bytearray()
    tb = title.encode("ascii", "replace")[:60]
    track += varlen(0) + b"\xFF\x03" + varlen(len(tb)) + tb
    track += varlen(0) + b"\xFF\x51\x03" + int(60_000_000 / BPM).to_bytes(3, "big")

    base = events[0][0]
    last = 0
    for ms, high, chan, d1, d2 in events:
        tick = int(round((ms - base) * TICKS_PER_MS))
        delta = max(0, tick - last)
        last = tick
        track += varlen(delta)
        if high in (0xC0, 0xD0):
            track += bytes([high | chan, d1 & 0x7F])
        else:
            track += bytes([high | chan, d1 & 0x7F, d2 & 0x7F])
    track += varlen(0) + b"\xFF\x2F\x00"

    header = (b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big")
              + (1).to_bytes(2, "big") + PPQ.to_bytes(2, "big"))
    data = header + b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)
    with open(out, "wb") as f:
        f.write(data)

    span = (events[-1][0] - events[0][0]) / 1000.0
    print(f"OK events={len(events)} span={span:.1f}s bytes={len(data)}")


if __name__ == "__main__":
    main()
