"""QuickXorHash, the content hash OneDrive reports for every file.

The algorithm (from Microsoft's published reference): a 160-bit register;
byte ``i`` of the input is XORed in at bit ``(i * 11) mod 160``, wrapping
around the register; finally the input length (64-bit little-endian) is
XORed into the last 8 bytes, and the 20 bytes are base64 encoded.

Because the bit position repeats every 160 bytes, the input is folded into a
160-byte accumulator first (fast XOR of big integers), then each of the 160
accumulated bytes is placed once. :func:`reference` is the plain byte-by-byte
form used to test the fast one.

Keepsake only uses this to avoid re-downloading after an upload; a mismatch
falls back to downloading and comparing SHA-256, so an error here can cost
time but never accepts a bad upload (ADR-0008).
"""

from __future__ import annotations

import base64

WIDTH = 160
SHIFT = 11
MASK = (1 << WIDTH) - 1
FOLD = 160  # bytes after which bit positions repeat


def _place(register: int, value: int, position: int) -> int:
    shifted = value << position
    if position + 8 > WIDTH:
        shifted |= value >> (WIDTH - position)
    return register ^ (shifted & MASK)


def _finish(register: int, length: int) -> str:
    raw = bytearray(register.to_bytes(WIDTH // 8, "little"))
    for i, b in enumerate(length.to_bytes(8, "little")):
        raw[WIDTH // 8 - 8 + i] ^= b
    return base64.b64encode(bytes(raw)).decode("ascii")


def reference(data: bytes) -> str:
    register = 0
    for i, b in enumerate(data):
        register = _place(register, b, (i * SHIFT) % WIDTH)
    return _finish(register, len(data))


class QuickXorHash:
    """Streaming QuickXorHash."""

    def __init__(self) -> None:
        self._acc = 0  # 160-byte accumulator as an integer, byte j = offset j mod 160
        self._length = 0
        self._pending = b""

    def update(self, data: bytes) -> None:
        # Keep the accumulator aligned to absolute offsets: fold only whole 160-byte blocks.
        data = self._pending + data
        whole = len(data) - len(data) % FOLD
        acc = self._acc
        view = memoryview(data)
        for start in range(0, whole, FOLD):
            acc ^= int.from_bytes(view[start : start + FOLD], "little")
        self._acc = acc
        self._pending = bytes(view[whole:])
        self._length += whole

    def digest_b64(self) -> str:
        acc_bytes = self._acc.to_bytes(FOLD, "little")
        register = 0
        for j, b in enumerate(acc_bytes):
            if b:
                register = _place(register, b, (j * SHIFT) % WIDTH)
        # Trailing partial block, at its absolute offsets.
        for k, b in enumerate(self._pending):
            register = _place(register, b, ((self._length + k) * SHIFT) % WIDTH)
        return _finish(register, self._length + len(self._pending))


def quickxor_file(path: str) -> str:
    h = QuickXorHash()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            h.update(chunk)
    return h.digest_b64()
