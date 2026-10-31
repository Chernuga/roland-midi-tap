"""tcplisten.py -- receive the ESP32 MIDI tap stream and log it.

The ESP32 connects to this listener and writes one line per USB-MIDI packet:

    [123456] RX 09 90 3C 40
    [128000] alive sent=99 buffered=0 wifi=3

Everything is appended to the log file, which the converter tools parse.

Usage:
    python tcplisten.py --log capture.log [--port 5005] [--host 0.0.0.0]
    python tcplisten.py --log capture.log --once      # exit after first session
"""
import argparse
import datetime
import socket
import sys


def serve(host, port, log_path, once):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(4)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(f"listening on {host}:{port} -> {log_path}", flush=True)

    with open(log_path, "a", encoding="utf-8", buffering=1) as f:
        f.write(f"\n=== listener start {datetime.datetime.now()} ===\n")
        while True:
            conn, addr = srv.accept()
            print(f"connection from {addr[0]}:{addr[1]}", flush=True)
            f.write(f"\n--- connection from {addr} at {datetime.datetime.now()} ---\n")
            conn.settimeout(2.0)
            buf = b""
            try:
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        text = line.decode("utf-8", "replace").strip()
                        if text:
                            f.write(text + "\n")
                            print(text, flush=True)
            except Exception as e:
                print(f"connection error: {e}", flush=True)
                f.write(f"connection error: {e}\n")
            finally:
                conn.close()
                print("connection closed", flush=True)
                f.write("--- closed ---\n")
            if once:
                print("--once set, exiting", flush=True)
                return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="capture.log")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--once", action="store_true",
                    help="exit after the first connection closes")
    a = ap.parse_args()
    try:
        serve(a.host, a.port, a.log, a.once)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
