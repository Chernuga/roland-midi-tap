"""Verify generated .mid files: event count, musical duration, size.

Usage: python verify.py <dir>
"""
import os
import sys

PPQ = 480
BPM = 120
TICKS_PER_SEC = PPQ * BPM / 60.0


def read_varlen(data, i):
    val = 0
    while True:
        b = data[i]
        i += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, i


def stats(path):
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        return None
    ti = data.find(b"MTrk")
    length = int.from_bytes(data[ti + 4:ti + 8], "big")
    trk = data[ti + 8:ti + 8 + length]
    i = 0
    t = 0
    status = None
    notes = 0
    total = 0
    while i < len(trk):
        delta, i = read_varlen(trk, i)
        t += delta
        b = trk[i]
        if b == 0xFF:
            i += 1
            meta = trk[i]; i += 1
            ln, i = read_varlen(trk, i)
            i += ln
            if meta == 0x2F:
                break
            continue
        if b & 0x80:
            status = b
            i += 1
        high = status & 0xF0
        need = 1 if high in (0xC0, 0xD0) else 2
        i += need
        total += 1
        if high == 0x90:
            notes += 1
    return total, notes, t / TICKS_PER_SEC, len(data)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    d = sys.argv[1]
    rows = []
    bad = 0
    for name in sorted(os.listdir(d)):
        if not name.lower().endswith(".mid"):
            continue
        try:
            st = stats(os.path.join(d, name))
        except PermissionError:
            rows.append((name, "LOCKED", "", "", ""))
            continue
        except Exception:
            rows.append((name, "INVALID", "", "", ""))
            bad += 1
            continue
        total, notes, secs, size = st
        rows.append((name, total, notes, f"{secs:.1f}", f"{size}"))
    print(f"{'file':<50} {'evts':>6} {'notes':>6} {'dur_s':>8} {'bytes':>7}")
    for r in rows:
        if r[1] == "INVALID":
            print(f"{r[0]:<50} INVALID")
        else:
            print(f"{r[0]:<50} {r[1]:>6} {r[2]:>6} {r[3]:>8} {r[4]:>7}")
    print(f"\nfiles={len(rows)} invalid={bad}")


if __name__ == "__main__":
    main()
