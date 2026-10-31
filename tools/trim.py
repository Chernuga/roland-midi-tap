"""Trim leading/trailing non-note events from our generated .mid files.

Because each capture window opens right after the previous extraction, the
previous track's teardown (all control-change, no notes) can land at the
start of the next file. This drops everything before the first Note On and
optionally everything after the last Note Off, then rewrites delta times.

Usage:
    python trim.py <file.mid> [<file2.mid> ...] [--keep-tail]
"""
import sys

PPQ = 480


def read_varlen(data, i):
    val = 0
    while True:
        b = data[i]
        i += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, i


def write_varlen(v):
    v = max(0, v)
    buf = bytearray([v & 0x7F])
    v >>= 7
    while v:
        buf.append((v & 0x7F) | 0x80)
        v >>= 7
    buf.reverse()
    return bytes(buf)


def parse(path):
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        raise ValueError("not a midi file")
    ti = data.find(b"MTrk")
    length = int.from_bytes(data[ti + 4:ti + 8], "big")
    track = data[ti + 8:ti + 8 + length]

    events = []
    i = 0
    t = 0
    status = None
    while i < len(track):
        delta, i = read_varlen(track, i)
        t += delta
        b = track[i]
        if b == 0xFF:
            i += 1
            meta = track[i]; i += 1
            ln, i = read_varlen(track, i)
            payload = track[i:i + ln]
            i += ln
            events.append((t, "meta", meta, payload))
            if meta == 0x2F:
                break
            continue
        if b & 0x80:
            status = b
            i += 1
        if status is None:
            raise ValueError("running status with no status")
        high = status & 0xF0
        need = 1 if high in (0xC0, 0xD0) else 2
        payload = track[i:i + need]
        i += need
        events.append((t, "chan", status, payload))
    return events


def is_note_on(ev):
    return ev[1] == "chan" and (ev[2] & 0xF0) == 0x90 and len(ev[3]) > 1 and ev[3][1] > 0


def is_note_off(ev):
    if ev[1] != "chan":
        return False
    h = ev[2] & 0xF0
    if h == 0x80:
        return True
    return h == 0x90 and len(ev[3]) > 1 and ev[3][1] == 0


def rebuild(events, path):
    first = next((k for k, e in enumerate(events) if is_note_on(e)), None)
    if first is None:
        return False
    last = max(k for k, e in enumerate(events) if is_note_off(e)) if any(is_note_off(e) for e in events) else len(events) - 1
    keep = [e for e in events[first:last + 1]]

    out = bytearray()
    out += write_varlen(0) + b"\xFF\x51\x03" + (60_000_000 // 120).to_bytes(3, "big")
    base = keep[0][0]
    prev = 0
    for t, kind, a, payload in keep:
        tt = t - base
        out += write_varlen(tt - prev)
        prev = tt
        if kind == "meta":
            out += bytes([0xFF, a]) + write_varlen(len(payload)) + payload
        else:
            out += bytes([a]) + payload
    out += write_varlen(0) + b"\xFF\x2F\x00"

    header = (b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big")
              + (1).to_bytes(2, "big") + PPQ.to_bytes(2, "big"))
    open(path, "wb").write(header + b"MTrk" + len(out).to_bytes(4, "big") + bytes(out))
    return True


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for p in args:
        try:
            evs = parse(p)
            before = len(evs)
            if rebuild(evs, p):
                evs2 = parse(p)
                print(f"trimmed {p}: {before} -> {len(evs2)} events")
            else:
                print(f"SKIP {p}: no note-on found")
        except Exception as e:
            print(f"FAIL {p}: {e}")


if __name__ == "__main__":
    main()
