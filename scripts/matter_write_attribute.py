#!/usr/bin/env python3
"""
Read or write a single Matter attribute via the Home Assistant Matter Server
WebSocket API. Standard library only - no pip installs.

WHAT IT IS FOR
    Home Assistant's Matter integration only surfaces the device attributes it
    has explicit support for. Vendor-specific configuration - notably Inovelli's
    parameter cluster on the VTM36 / VTM30-SN (cluster 0x122FFC31, attribute
    0x122F00NN == Inovelli parameter NN) - has no HA entity, so it must be
    written directly on the Matter Server.

    See guides/inovelli_fan_canopy.md ("identical across every room") for the
    exact attribute/value each canopy needs.

WHO CALLS IT
    An operator, by hand, from a machine on the LAN (typically the Mac Mini).
    Nothing in HA invokes this. It is not a shell_command target.

PREREQUISITES
    - Python 3.9+
    - Network reachability to the HA host on TCP 5580

SECURITY
    The Matter Server WebSocket API (port 5580) is UNAUTHENTICATED and bound for
    the local network - it exists for the HA Matter integration to talk to the
    add-on. This script uses that same open endpoint. Anyone on the LAN can
    already reach it; this adds no new exposure, but do not forward 5580 off the
    LAN and do not run this against a host you do not control. A bad write can
    misconfigure a device (wrong dimmer curve, wrong power-on behaviour); always
    note the pre-write value this script prints so you can restore it.

EXAMPLES
    # Read Inovelli param 24 (Light Minimum Dim) on Avery's canopy (node 10):
    python3 scripts/matter_write_attribute.py --node 10 \
        --cluster 305134641 --attribute 305070104 --read-only

    # Set it to 33 (~13% floor):
    python3 scripts/matter_write_attribute.py --node 10 --endpoint 1 \
        --cluster 305134641 --attribute 305070104 --value 33

    # Full path form instead of --endpoint/--cluster/--attribute:
    python3 scripts/matter_write_attribute.py --node 10 \
        --path 1/305134641/305070104 --value 33
"""

import argparse
import base64
import json
import os
import socket
import struct
import sys
import uuid
from urllib.parse import urlparse


# --- Minimal RFC 6455 text-frame client (ws://, no TLS, no extensions) ---------

class WS:
    def __init__(self, url: str, timeout: float):
        u = urlparse(url)
        if u.scheme != "ws":
            raise ValueError("only ws:// is supported (the Matter Server API is plain ws)")
        host = u.hostname
        port = u.port or 80
        path = u.path or "/"
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        resp = self._read_until(b"\r\n\r\n")
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"handshake failed: {resp.split(chr(13).encode(), 1)[0]!r}")
        self._buf = b""

    def _read_until(self, marker: bytes) -> bytes:
        data = b""
        while marker not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed during handshake")
            data += chunk
        return data

    def _recv_exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("connection closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send_text(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x81])  # FIN + opcode 1 (text)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv_text(self) -> str:
        """Return the next complete text message, answering pings, ignoring binary."""
        chunks = []
        while True:
            b0, b1 = self._recv_exact(2)
            fin = b0 & 0x80
            opcode = b0 & 0x0F
            masked = b1 & 0x80
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            mask = self._recv_exact(4) if masked else b""
            data = self._recv_exact(length)
            if masked:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))

            if opcode == 0x8:  # close
                raise ConnectionError("server closed the connection")
            if opcode == 0x9:  # ping -> pong
                self._send_control(0x8A, data)
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode in (0x0, 0x1):  # continuation / text
                chunks.append(data)
                if fin:
                    return b"".join(chunks).decode()
                continue
            # opcode 0x2 (binary) or unknown: skip
            if fin:
                chunks = []

    def _send_control(self, first_byte: int, payload: bytes) -> None:
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes([first_byte, 0x80 | len(payload)]) + mask + masked)

    def close(self) -> None:
        try:
            self._send_control(0x88, b"")
        except OSError:
            pass
        self.sock.close()


# --- Matter Server command helpers -------------------------------------------

def send_command(ws: WS, command: str, args: dict):
    message_id = uuid.uuid4().hex
    ws.send_text(json.dumps({"message_id": message_id, "command": command, "args": args}))
    while True:
        msg = json.loads(ws.recv_text())
        if msg.get("message_id") != message_id:
            continue  # unsolicited event or other traffic
        if "error_code" in msg:
            raise RuntimeError(f"{command} failed: {msg.get('error_code')} {msg.get('details', '')}")
        return msg.get("result")


def build_path(args) -> str:
    if args.path:
        return args.path
    if args.cluster is None or args.attribute is None:
        sys.exit("Provide --path, or all of --endpoint --cluster --attribute.")
    return f"{args.endpoint}/{args.cluster}/{args.attribute}"


def parse_value(raw: str):
    low = raw.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    if low.startswith("0x"):
        return int(low, 16)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--host", default="homeassistant.lan",
                   help="Matter Server host (default: homeassistant.lan)")
    p.add_argument("--url", help="Full ws:// URL, overrides --host")
    p.add_argument("--node", type=int, required=True, help="Matter node id")
    p.add_argument("--path", help="endpoint/cluster/attribute, all decimal")
    p.add_argument("--endpoint", type=int, default=1, help="Endpoint (default: 1)")
    p.add_argument("--cluster", type=int, help="Cluster id, decimal")
    p.add_argument("--attribute", type=int, help="Attribute id, decimal")
    p.add_argument("--value", help="Value to write (int, 0x hex, or true/false)")
    p.add_argument("--read-only", action="store_true", help="Read and print, do not write")
    p.add_argument("--timeout", type=float, default=10.0)
    args = p.parse_args()

    if not args.read_only and args.value is None:
        sys.exit("Give --value to write, or --read-only to just read.")

    url = args.url or f"ws://{args.host}:5580/ws"
    path = build_path(args)

    ws = WS(url, timeout=args.timeout)
    try:
        info = json.loads(ws.recv_text())  # ServerInfoMessage on connect
        print(f"connected: {url}  schema={info.get('schema_version')} "
              f"sdk={info.get('sdk_version')} fabric={info.get('fabric_id')}")

        before = send_command(ws, "read_attribute",
                              {"node_id": args.node, "attribute_path": path})
        print(f"node {args.node}  {path}  before: {before}")

        if args.read_only:
            return 0

        value = parse_value(args.value)
        send_command(ws, "write_attribute",
                     {"node_id": args.node, "attribute_path": path, "value": value})
        after = send_command(ws, "read_attribute",
                             {"node_id": args.node, "attribute_path": path})
        print(f"node {args.node}  {path}  after:  {after}  (wrote {value!r})")

        ok = after == value or (isinstance(value, bool) and after in (0, 1, True, False))
        if not ok:
            print("WARNING: read-back does not match the written value.", file=sys.stderr)
            return 2
        return 0
    finally:
        ws.close()


if __name__ == "__main__":
    raise SystemExit(main())
