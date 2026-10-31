"""Build MANIFEST.txt for the captured Roland MIDI files."""
import os
import re
import sys

PPQ = 480
BPM = 120
TICKS_PER_SEC = PPQ * BPM / 60.0
NAME_RE = re.compile(r"^(\d{2})_(.+)_(\d{2}-\d{2}-\d{4})_(\d+)s\.mid$")


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
        i += 1 if high in (0xC0, 0xD0) else 2
        total += 1
        if high == 0x90:
            notes += 1
    return total, notes, t / TICKS_PER_SEC, len(data)


def fmt(sec):
    return f"{int(sec)//60}:{int(sec)%60:02d}"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    d = sys.argv[1]
    rows = []
    for name in sorted(os.listdir(d)):
        m = NAME_RE.match(name)
        if not m:
            continue
        num, title, date, declared = m.group(1), m.group(2), m.group(3), int(m.group(4))
        try:
            total, notes, secs, size = stats(os.path.join(d, name))
        except PermissionError:
            continue
        rows.append((int(num), title, date, declared, total, notes, secs, size, name))

    lines = []
    lines.append("ROLAND PIANO APP -- RECORDINGS EXTRACTED AS MIDI")
    lines.append("=" * 78)
    lines.append("")
    lines.append("Source      : Roland Piano App 'My recordings' (Guest profile)")
    lines.append("Capture     : ESP32-S3 posing as a USB-MIDI 'Roland Digital Piano'")
    lines.append("              (VID 1410 / PID 0290); every packet the app sent was")
    lines.append("              logged over WiFi/TCP and converted to Standard MIDI Files.")
    stamps = []
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        try:
            stamps.append(os.path.getmtime(p))
        except OSError:
            pass
    import datetime as _dt
    if stamps:
        lo = _dt.datetime.fromtimestamp(min(stamps)).strftime("%Y-%m-%d %H:%M")
        hi = _dt.datetime.fromtimestamp(max(stamps)).strftime("%Y-%m-%d %H:%M")
        lines.append(f"Captured    : {lo} .. {hi} (local time of this PC)")
    else:
        lines.append("Captured    : (no files)")
    lines.append("")
    lines.append("Format      : Standard MIDI File, Format 0, 480 PPQ, 120 BPM header tempo")
    lines.append("Contents    : Note On/Off, plus any control-change / pitch-bend / aftertouch")
    lines.append("              the app transmitted. No SysEx was sent by the app.")
    lines.append("")
    lines.append("Note on tempo: the app does not transmit a tempo, so the files are")
    lines.append("written at a nominal 120 BPM. The ratio of note timings is exact;")
    lines.append("absolute playback speed corresponds to 120 BPM.")
    lines.append("")
    lines.append("Cleanup     : leading 'teardown' controller dumps (carried over from the")
    lines.append("              previous track) were trimmed so each file starts at its")
    lines.append("              first Note On.")
    lines.append("")
    lines.append("-" * 78)
    lines.append(f"{'#':>2}  {'Title':<26} {'Date':<11} {'App':>6} {'MIDI':>6} {'Evts':>6} {'Notes':>6} {'KB':>6}")
    lines.append("-" * 78)
    for num, title, date, declared, total, notes, secs, size, name in rows:
        lines.append(f"{num:>2}  {title[:26]:<26} {date:<11} {fmt(declared):>6} "
                     f"{fmt(secs):>6} {total:>6} {notes:>6} {size/1024:>6.1f}")
    lines.append("-" * 78)
    total_notes = sum(r[5] for r in rows)
    total_evts = sum(r[4] for r in rows)
    total_secs = sum(r[6] for r in rows)
    total_bytes = sum(r[7] for r in rows)
    lines.append(f"Tracks: {len(rows)}   events: {total_evts}   notes: {total_notes}   "
                 f"music: {fmt(total_secs)}   size: {total_bytes/1024/1024:.2f} MB")
    lines.append("")
    lines.append("'App' = duration shown in the app; 'MIDI' = measured first-to-last event.")
    lines.append("Small differences are the app's trailing silence, which contains no notes.")
    out = os.path.join(d, "MANIFEST.txt")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
