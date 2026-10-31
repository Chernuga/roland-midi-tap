"""Convert the ESP32 MIDI capture log into a Standard MIDI File.

USB-MIDI packet lines look like:
    [118842] RX 09 90 39 4A
    header 0x09 = cable0/NoteOn, status 0x90, note 0x39, velocity 0x4A

Usage:
    python log2mid.py <in.log> <out.mid> [--split-gap SECONDS]
"""
import argparse
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


def parse(path):
    events = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = PACKET.search(line)
        if not m:
            continue
        ms = int(m.group(1))
        h = int(m.group(2), 16)
        status = int(m.group(3), 16)
        d1 = int(m.group(4), 16)
        d2 = int(m.group(5), 16)
        cin = h & 0x0F
        high = status & 0xF0
        # skip sysex / realtime / junk for now
        if high in (0x80, 0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0):
            events.append((ms, high, status & 0x0F, d1, d2))
    return events


def split_tracks(events, gap_ms):
    """Split on silence gaps > gap_ms."""
    if not events:
        return []
    groups = [[events[0]]]
    for prev, cur in zip(events, events[1:]):
        if cur[0] - prev[0] > gap_ms:
            groups.append([])
        groups[-1].append(cur)
    return [g for g in groups if len(g) >= 4]


def write_mid(events, out_path, name=""):
    track = bytearray()
    track += varlen(0) + b"\xFF\x03" + varlen(len(name)) + name.encode("ascii", "replace")
    track += varlen(0) + b"\xFF\x51\x03" + int(60_000_000 / BPM).to_bytes(3, "big")

    base = events[0][0]
    last_tick = 0
    for ms, high, chan, d1, d2 in events:
        tick = int(round((ms - base) * TICKS_PER_MS))
        delta = max(0, tick - last_tick)
        last_tick = tick
        track += varlen(delta)
        if high in (0xC0, 0xD0):
            track += bytes([high | chan, d1 & 0x7F])
        else:
            track += bytes([high | chan, d1 & 0x7F, d2 & 0x7F])
    track += varlen(0) + b"\xFF\x2F\x00"

    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") \
             + (1).to_bytes(2, "big") + PPQ.to_bytes(2, "big")
    trk = b"MTrk" + len(track).to_bytes(4, "big") + bytes(track)
    with open(out_path, "wb") as f:
        f.write(header + trk)
    return len(events)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--split-gap", type=float, default=0.0,
                    help="split into multiple files on silent gaps (seconds)")
    a = ap.parse_args()

    events = parse(a.infile)
    if not events:
        sys.exit("no MIDI events found")

    if a.split_gap <= 0:
        n = write_mid(events, a.outfile, "capture")
        span = (events[-1][0] - events[0][0]) / 1000.0
        print(f"wrote {a.outfile}: {n} events, {span:.1f}s")
        return

    groups = split_tracks(events, a.split_gap * 1000.0)
    print(f"{len(groups)} group(s)")
    stem = a.outfile.rsplit(".", 1)[0]
    for i, g in enumerate(groups, 1):
        out = f"{stem}_{i:02d}.mid"
        n = write_mid(g, out, f"track{i}")
        span = (g[-1][0] - g[0][0]) / 1000.0
        print(f"  {out}: {n} events, {span:.1f}s")


if __name__ == "__main__":
    main()
