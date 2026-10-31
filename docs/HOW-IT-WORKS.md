# How it works — and what didn't

Notes from reverse-engineering the Roland Piano App (v1.5.9, Android 13,
Xiaomi/Redmi). Useful if you are trying to liberate data from a similarly
locked-down app.

## The target

`jp.co.roland.RolandPianoApp` keeps user recordings in **"My recordings"**.
The app is account-aware: a *Guest* profile and a *Roland account* profile each
have their own set. Logging in does **not** migrate or sync recordings — it
just gives you a second, empty list.

Roland's support documentation is explicit:

> "it is not possible to share or export a recording that has been created with
> the Roland Piano App, via the app or email."
>
> "A recording created via the app remains stored within the app and can only be
> accessed using the app."

## What was tried, in order

### 1. Read the private data directory

```
adb shell ls /data/user/0/jp.co.roland.RolandPianoApp
  -> Permission denied
```

The shell user is `uid=2000(shell)`. App directories are `drwx------ u0_aXXX`.
The block happens at `open()`, so `cat`, `dd`, `cp`, `adb pull` all fail
identically. There is no "byte-by-byte" trick; the directory cannot be
traversed.

**Note the distinction** that cost the most time: `/sdcard/Android/data/<pkg>`
("app-specific *external* storage") **is** world-traversable and is what you
read for apps like BiliBili. Private internal storage (`/data/data/<pkg>`) is
not. Roland writes only to the latter — that directory does not even exist on
shared storage.

### 2. `adb backup`

```
adb backup -f roland.ab --noapk jp.co.roland.RolandPianoApp
```

The phone shows *"Full backup"* and the package is scoped correctly, but:

```
bmgr backupnow jp.co.roland.RolandPianoApp
  -> "Backup is not allowed"
```

The app opts out via backup rules despite `ALLOW_BACKUP` appearing in its
flags. On Android 12+ `adb backup` is largely neutered anyway.

### 3. Virtual MIDI device (`MidiDeviceService`)

The most promising idea: publish a virtual MIDI device, let the app connect to
it, and log everything.

A minimal sideloadable app was built (Java, compiled with `javac` + `d8` +
`aapt2` + `apksigner`, no Gradle) that registered a `MidiDeviceService` with
`input-port` and `output-port`.

Result: **the app connected to it and sent nothing.** Zero bytes.

Escalation — spoofing the identity to match the piano exactly:

```xml
<device name="Roland Roland Digital Piano" manufacturer="Roland"
        product="Roland Digital Piano" version="1.00">
```

Android then showed *two* devices with identical names, and the app opened a
handle to the fake one — but still transmitted nothing, and never opened a
port (`Status: null`).

**Root cause**, found by diffing `dumpsys midi` properties:

| Property | Real USB piano | Virtual device |
|---|---|---|
| `alsa_card` | `1` | absent |
| `alsa_device` | `0` | absent |
| `usb_device` | `UsbDevice[VID 1410]` | absent |
| `mType` | `1` (USB) | `2` (virtual) |

Those properties are injected by Android's `UsbMidiDevice` / `AlsaMidiDevice`
implementations. **An app cannot set them.** The Roland app filters devices on
them, so a virtual device can never pass the filter. This is a hard
architectural dead end, not a handshake problem.

### 4. Co-owning the USB MIDI port

```
mInputPortOpen=[true]      <- exclusive, one owner
mOutputPortOpenCount=[1]   <- output ports are counted, so shareable
```

The app holds the *input* port (phone -> piano): the exclusive one. A second
opener gets `null`. The shareable output port carries piano -> phone, which is
not what we want.

### 5. Kernel-level access

```
/dev/snd/midiC1D0        crw-rw---- system audio   -> not in shell's groups
/dev/bus/usb/001/002     crw-rw---- root   usb     -> not in shell's groups
usbmon                   requires debugfs (root)
```

SELinux is `Enforcing`. Dead end without root.

### 6. Modify the APK and keep the data

Impossible: changing the APK invalidates the signature, a re-signed APK is
treated as a different app, and uninstalling to install it deletes the data you
were trying to save. Signature-check bypass modules all require root.

### 7. Root

Technically possible, but Xiaomi's bootloader unlock **factory-resets the
device first**. Root arrives after the data is already gone.

### 8. Windows as a BLE-MIDI peripheral

Initially dismissed, then re-tested properly:

```
BluetoothAdapter.is_peripheral_role_supported = True
GattServiceProvider.create_async(BLE-MIDI service) = 0 (success)
characteristic 7772E5DB-... created = 0
start_advertising() = OK
```

Windows **can** advertise BLE-MIDI (the earlier failure was
`BluetoothLEAdvertisementPublisher` with a bare payload, which really does
fail with `E_INVALIDARG` on this Intel adapter — `GattServiceProvider` works).

The app scanned and reported *"We found no pianos"*, because it launches a
**filtered** BLE scan (`BtGatt.GattService: start scan with filters`) that our
advertisement did not match. The PC's Bluetooth name is the computer name, and
renaming it needs admin.

This route may well work for someone with admin rights on the PC. It was
abandoned here because the USB route succeeded first.

### 9. USB MIDI host on the PC

`midicapture.py` (pure `winmm`) will record from any MIDI input. But when the
app talks to the piano over USB, the *phone* is the USB host — the PC cannot
also be on that cable, and USB is strictly point-to-point.

### 10. What actually worked: be the piano

The phone's USB host stack enumerates the ESP32-S3 as a genuine USB-MIDI
device when the firmware presents the right descriptors. Android therefore
populates `alsa_card`, `alsa_device`, `usb_device` and `mType=1` — **the exact
properties the app filters on**.

```
VID 0x1410 / PID 0x0290
manufacturer  "Roland"
product       "Roland Digital Piano"
serial        "RDP000001"
```

The app connected immediately and streamed note data. `dumpsys midi` showed:

```
Device Info: mType=1 ... manufacturer=Roland ...
  mInputPortOpen=[true]  mOutputPortOpenCount=[1]
Clients:
  Client: UID 10465 PID <app>  Device Connections: <device N>
```

Notably **no SysEx handshake** was sent — the app does not query device
identity. It opened the port and started sending note on/off.

## The capture format

Each USB-MIDI event packet is 4 bytes: `header, status, data1, data2`, where
`header` encodes cable number (high nibble) and code index (low nibble).

The firmware logs each packet as one line:

```
[123456] RX 09 90 3C 40
          |  |  |  |  +-- velocity 0x40
          |  |  |  +----- note 0x3C (60 = middle C)
          |  |  +-------- status 0x90 = Note On, channel 1
          |  +----------- header 0x09 = cable 0, CIN 9 (Note On)
          +-------------- milliseconds since boot
```

The converters rebuild tick times from those millisecond stamps.

## Gotcha: per-track segmentation

The app dumps a burst of **30–65 control-change messages** when playback stops
(pedal release, all-notes-off). Because each capture window opens right after
the previous extraction, that teardown lands at the start of the *next* file.

`tools/trim.py` drops everything before the first Note On, so every file starts
cleanly on its first note.

## Gotcha: tempo

The app never transmits a tempo meta-event, so a "correct" BPM is unknown.
Files are written at 120 BPM. If a 2:22 recording should last 2:22, the note
spacing is already right at that tempo — but the *absolute* tempo is arbitrary.
Adjust the file tempo if it sounds wrong; do not rescale the notes.
