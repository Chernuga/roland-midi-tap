# Roland MIDI Tap

Recover the recordings trapped inside the **Roland Piano App** as real `.mid`
files — by having a cheap ESP32-S3 pretend to be the piano.

The app can record your playing but offers **no export of any kind**: no share
button, no save-as, no USB transfer, no cloud sync of recordings. Roland's own
documentation says a recording "remains stored within the app and can only be
accessed using the app".

This project extracts them anyway, with no root and no modification to the app.

```
Roland Piano App  --USB MIDI-->  ESP32-S3 (poses as the piano)  --WiFi-->  PC  -->  .mid
```

---

## Why this works

Android blocks every software route:

| Attempt | Result |
|---|---|
| Read the app's private data dir | `Permission denied` (app sandbox) |
| `adb backup` | *"Backup is not allowed"* (app opts out) |
| Virtual MIDI device (`MidiDeviceService`) | App ignores it — it filters for real USB/ALSA devices |
| Co-own the USB MIDI port | Ports are exclusive |
| Read `/dev/snd/midiC1D0` | Not in the `audio` group |
| Modify the APK | Invalidates the signature |

But the app **does** send genuine USB-MIDI to whatever instrument is attached.
So attach something that answers to the right USB descriptors and record the
stream. That is what the firmware does:

```
VID 0x1410 / PID 0x0290   (Roland)
manufacturer "Roland"
product      "Roland Digital Piano"
```

The app connects and streams every note-on / note-off / pedal event over bulk
USB endpoints. The ESP32 forwards those packets over WiFi to the PC, where they
become Standard MIDI Files.

---

## Requirements

* **ESP32-S3** board with native USB (ESP32-S2/C3 also work; plain ESP32 does **not**)
* A **USB-C/Micro-USB OTG adapter** to plug the board into the phone
* Python 3 on the PC
* Arduino ESP32 core (`arduino-cli core install esp32:esp32`)
* Phone and PC on the **same WiFi network**

---

## Quick start

```powershell
# 1. check your environment
.\roland-tap.ps1 setup

# 2. tell it your WiFi + PC address (writes config.json + firmware secrets.h)
.\roland-tap.ps1 config

# 3. build and flash the firmware (board on the PC via its UART port)
.\roland-tap.ps1 build
.\roland-tap.ps1 flash

# 4. start the listener
.\roland-tap.ps1 listen

# 5. move the board to the PHONE (native USB port -> OTG adapter)
#    open the Roland app -> Connection -> Cable (USB)

# 6. describe your recordings, then play them one at a time
.\roland-tap.ps1 record

# 7. check the results
.\roland-tap.ps1 verify
```

Or just run `.\roland-tap.ps1` for an interactive menu.

### `tracks.csv`

The recorder reads a simple list so it can name and verify each file:

```csv
num,title,date,duration
1,Adagio,31/05/2026,02:22
2,Hello,31/05/2026,01:26
```

For each row it prompts you to play that track, then splits exactly that
segment out of the live stream, writes `01_Adagio_31-05-2026_142s.mid`, trims
the leading controller noise, and reports events / span / size.

---

## Commands

| Command | What it does |
|---|---|
| `setup` | Verify python, esptool, arduino-cli, ESP32 core, serial port |
| `config` | Store WiFi credentials and PC address |
| `build` | Generate `secrets.h` and compile the firmware |
| `flash` | Upload to the board over its serial port |
| `listen` | Start the TCP listener (port 5005) in the background |
| `stop` | Stop the listener |
| `record` | Interactive per-track capture guided by `tracks.csv` |
| `convert` | Turn a whole capture log into MIDI (optionally split on silence) |
| `verify` | Validate every `.mid` and regenerate `MANIFEST.txt` |
| `open` | Open the output folder |

---

## Output

* Standard MIDI File, **Format 0, 480 PPQ**
* Note on/off, control change (sustain etc.), pitch bend, aftertouch
* The app does **not** transmit tempo, so files are written at a nominal
  **120 BPM**. Note timing *ratios* are exact; if playback sounds fast or slow,
  change the tempo of the MIDI file, not the notes.
* `MANIFEST.txt` records source title, date, app duration, measured duration,
  event and note counts.

---

## Limitations

* **One USB connection at a time.** The board is powered from the phone's OTG
  port; do not also connect its UART port unless your board has VBUS backfeed
  protection (use `firmware/RolandTapSerial` only for bench debugging).
* **WiFi credentials are compiled into the firmware** (`secrets.h`, gitignored).
* The app must be playing to the ESP32, which means **the piano produces no
  sound** during capture — you are recording the note stream, not audio.
* Requires the app to accept a USB connection, i.e. the phone must be in
  "Cable (USB)" mode.

---

## Layout

```
roland-tap.ps1              terminal UI / orchestration
firmware/RolandTap/         ESP32-S3 firmware (WiFi telemetry)
firmware/RolandTapSerial/   ESP32-S3 firmware (UART telemetry, debug)
tools/tcplisten.py          TCP server receiving the stream
tools/seg2mid.py            extract one segment -> .mid
tools/log2mid.py            whole log -> .mid (optional silence split)
tools/trim.py               strip leading controller dumps
tools/verify.py             validate + summarise
tools/manifest.py           write MANIFEST.txt
docs/HOW-IT-WORKS.md        the reverse-engineering notes
```

## License

MIT — see [LICENSE](LICENSE).

Not affiliated with Roland. For recovering your own recordings from your own
device.
