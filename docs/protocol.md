# Replication protocol

Version 1. It freezes at the end of slice 18 (ADR-0057); after that, changes are an escalation item (CLAUDE.md, v2 additions).

## Transport (ADR-0054)

- TCP, default port 47110, to a LAN or VPN overlay address.
- TLS 1.2, cipher `ECDHE-PSK-CHACHA20-POLY1305` only, with no compression.
- The PSK identity is the connecting device's ID:
  - for a paired device, the key is the 256-bit link key agreed at pairing;
  - for pairing, the identity is `keepsake-pair/1` with a public key, accepted only while the pairing window is open.

## Frames

- **Control frame:** a 4-byte big-endian length, then a UTF-8 JSON object of at most 64 KiB with a `type`.
- **Raw bytes:** an answer may be `{"type": "blob", "size": n, ...}` followed by exactly *n* raw bytes, at most 64 MiB.
- **Refusals:** an `error` frame (`{"type": "error", "reason": "..."}`) is a refusal. The reason never holds a local path.

## Pairing (ADR-0054)

| Step | From | Frame |
|---|---|---|
| 1 | initiator | `pair-commit`: `v`, `deviceId`, `name`, `commit` (hex SHA-256 of a 32-byte nonce) |
| 2 | responder | `pair-nonce`: `deviceId`, `name`, `nonce` (hex, 32 bytes) |
| 3 | initiator | `pair-reveal`: `nonce` (checked against the commitment) |
| 4 | both | `pair-confirm`: `ok`, once the user has compared the code |
| 5 | initiator | `pair-key`: `key` (hex, 32 bytes), only if both said yes |
| 6 | responder | `pair-done` |

The code is computed like this:

```
SHA-256("keepsake sas v1" || len||tls-unique || len||nonce_i || len||nonce_r || len||id_i || len||id_r)
```

Each `len` is a 4-byte big-endian length. The first 8 bytes of the digest are read as a big-endian number, and the code is that number modulo 1,000,000, written as 6 digits.

## Session

1. The client sends `hello` with `v`, `deviceId` (it must match the PSK identity), `name` and `wake` (up to 4 hardware addresses). The server answers with its own `hello`.
2. `ping` is answered by `pong`.

## Transfers (ADR-0057)

| Request | Answer |
|---|---|
| `{"type": "manifest", "share": id}` | `blob` with `root`, followed by the manifest's canonical JSON |
| `{"type": "chunk", "share": id, "path": p, "index": i}` | `blob` with `path` and `index`, followed by the chunk's bytes |

Both are refused unless the share is offered to the asking device. A chunk is refused if its file changed since the offer.

### Manifest

```json
{
  "version": 1,
  "chunk": 4194304,
  "entries": [
    {"path": "bin", "type": "dir", "mode": 493, "mtime": 1600000000000000000},
    {"path": "bin/game.exe", "type": "file", "mode": 420, "mtime": 1600000000123456789,
     "size": 10242, "sha256": "...", "chunks": ["..."]},
    {"path": "data/current.pak", "type": "link", "mode": 511, "mtime": 0, "target": "levels/one.pak"}
  ],
  "root": "..."
}
```

- **The root:** `root` is the SHA-256 of the canonical JSON without `root` (sorted keys, no spaces, ASCII).
- **Chunks:** a file's chunks are 4 MiB, the last one shorter. A chunk whose hash is that of all zeros of its length is never requested.
