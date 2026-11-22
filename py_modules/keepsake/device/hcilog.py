"""Signs in an HCI capture (btsnoop, datalink 2001) for the reconnect diagnosis (ADR-0082, ADR-0083).

The helper captures the monitor channel; this reads it without any binary. It looks only for
the few things that tell the outcomes apart:

- ``connect-request``: the controller paged this handheld (HCI Connection Request);
- ``link-key-reply`` / ``link-key-negative``: BlueZ answered with a stored key, or had none (O4);
- ``encrypted``: Encryption Change with encryption on;
- ``security-block``: L2CAP Connection Response "security block" (O3, the SSP timing race);
- ``auth-failure``: Disconnection Complete with reason Authentication Failure (O2);
- ``sdp``: L2CAP Connection Request for PSM 1 (part of O5).
"""

from __future__ import annotations

import struct

HEADER = b"btsnoop\x00"
MON_COMMAND, MON_EVENT, MON_ACL_TX, MON_ACL_RX = 2, 3, 4, 5
EV_CONNECTION_REQUEST, EV_DISCONNECTION, EV_ENCRYPTION = 0x04, 0x05, 0x08
OP_LINK_KEY_REPLY, OP_LINK_KEY_NEGATIVE = 0x040B, 0x040C
REASON_AUTH_FAILURE = 0x05


def records(data: bytes) -> list[tuple[int, int, bytes]]:
    """``(index, monitor opcode, payload)`` for each record; an unreadable tail is ignored."""
    if not data.startswith(HEADER) or len(data) < 16:
        return []
    out = []
    at = 16
    while at + 24 <= len(data):
        _orig, incl, flags, _drops, _stamp = struct.unpack(">IIIIQ", data[at : at + 24])
        payload = data[at + 24 : at + 24 + incl]
        if len(payload) < incl:
            break
        out.append((flags >> 16, flags & 0xFFFF, payload))
        at += 24 + incl
    return out


def _l2cap_signals(acl: bytes) -> list[tuple[int, bytes]]:
    """Signalling commands in one ACL packet: ``(code, data)``."""
    if len(acl) < 8:
        return []
    _length, cid = struct.unpack("<HH", acl[4:8])
    if cid != 0x0001:
        return []
    out = []
    at = 8
    while at + 4 <= len(acl):
        code, _ident, size = struct.unpack("<BBH", acl[at : at + 4])
        out.append((code, acl[at + 4 : at + 4 + size]))
        at += 4 + size
    return out


def signs(data: bytes) -> set[str]:
    found: set[str] = set()
    for _index, opcode, payload in records(data):
        if opcode == MON_EVENT and payload:
            event = payload[0]
            if event == EV_CONNECTION_REQUEST:
                found.add("connect-request")
            elif (
                event == EV_DISCONNECTION
                and len(payload) >= 6
                and payload[2] == 0
                and payload[5] == REASON_AUTH_FAILURE
            ):
                found.add("auth-failure")
            elif event == EV_ENCRYPTION and len(payload) >= 6 and payload[2] == 0 and payload[5]:
                found.add("encrypted")
        elif opcode == MON_COMMAND and len(payload) >= 2:
            (command,) = struct.unpack("<H", payload[:2])
            if command == OP_LINK_KEY_REPLY:
                found.add("link-key-reply")
            elif command == OP_LINK_KEY_NEGATIVE:
                found.add("link-key-negative")
        elif opcode in (MON_ACL_TX, MON_ACL_RX):
            for code, body in _l2cap_signals(payload):
                if code == 0x02 and len(body) >= 2 and struct.unpack("<H", body[:2])[0] == 0x0001:
                    found.add("sdp")
                if code == 0x03 and len(body) >= 6 and struct.unpack("<H", body[4:6])[0] == 0x0003:
                    found.add("security-block")
    return found
