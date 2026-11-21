# Replication protocol

Version 1, **frozen** at the end of slice 18 (ADR-0058). `tests/test_replication_protocol.py` pins the values below. A change needs a new version and an ADR; it is an escalation item (CLAUDE.md, v2 additions).

## Transport (ADR-0054)

- TCP, default port 47110, to a LAN or VPN overlay address.
- TLS 1.2, cipher `ECDHE-PSK-CHACHA20-POLY1305` only, with no compression.
- The PSK identity is the connecting device's ID:
  - for a paired device, the key is the 256-bit link key agreed at pairing;
  - for pairing, the identity is `keepsake-pair/2` with a public key, accepted while the listener is on, at most 3 in 2 minutes, never from a locked-out address (ADR-0070).

## Frames

- **Control frame:** a 4-byte big-endian length, then a UTF-8 JSON object of at most 64 KiB with a `type`.
- **Raw bytes:** an answer may be `{"type": "blob", "size": n, ...}` followed by exactly *n* raw bytes, at most 64 MiB.
- **Refusals:** an `error` frame (`{"type": "error", "reason": "..."}`) is a refusal. The reason never holds a local path.

## Pairing (ADR-0070, pairing protocol 2)

| Step | From | Frame |
|---|---|---|
| 1 | requester | `pair-request`: `v` (2), `deviceId`, `name` |
| 2 | receiver | `pair-accepted`: `deviceId`, `name`, once the user pressed Accept; or `pair-declined`: `reason` (`declined`, `timed out`) |
| 3 | both | twenty rounds, *i* = 0 to 19, one per bit of the code: requester `pair-c` (`i`, `c`), receiver `pair-c`, requester `pair-n` (`i`, `n`), then the receiver checks and sends its `pair-n`, and the requester checks |
| 4 | requester | `pair-key`: `key` (hex, 32 bytes), only once every round matched |
| 5 | receiver | `pair-done` |

The code is a random 6-digit number shown only on the receiver and typed on the requester. Bit *i* is `(code >> i) & 1`. Each commitment is:

```
HMAC-SHA256(key = nonce (16 random bytes),
            "keepsake passkey v1" || len||tls-unique || len||requester id || len||receiver id
            || len||role ("req" or "recv") || len||(i, bit as two big-endian uint32))
```

Lengths are 4-byte big-endian. A commitment that does not match the sender's revealed nonce and the checker's own bit ends the attempt with `error` ("the code was wrong").

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

## Pulling

- **Streams:** a receiver opens up to 4 connections, each with one request in flight. Streams may go to several devices offering the same root hash (ADR-0058).
- **Order:** chunks may be requested in any order. A sender answers each one on its own, so a receiver may ask again after any failure.

## Additions to version 1 (ADR-0059)

Only new request types are added under version 1. A device that does not know one answers `error` with `unknown request`.

| Request | Answer |
|---|---|
| `{"type": "offer", "offer": {...}}` | `{"type": "offer-received", "id": offer id}` |

The offer holds:
- `id` (16 hex), `title`, `from.name`;
- `shares`: per scope (`install`, `prefix`, `tool`, `art`) a `share`, its manifest `root` and `bytes`;
- `exe` and `startDir`: a scope and a relative path;
- `launchOptions`, with only the placeholders `{install}`, `{prefix}` and `{home}`;
- `compatTool`;
- `art`: an asset type from 0 to 3, and a file name;
- `gameKey` and `savesEnabled`.

It never holds an absolute path.

Later additions (each a new request type, or an optional field that older devices ignore; ADR-0072 section 8):

| Request | Answer | Added |
|---|---|---|
| `{"type": "offer-state", "id", "state", "reason", "stage", "done", "total", "bytesPerSecond", "secondsLeft"}` | `{"type": "offer-state-received", "id"}` | v0.30.2 (state and reason); v0.31.0 (the bar's numbers, optional) |
| `{"type": "space-check", "bytes": {scope: n}, "compatTool"}` | `{"type": "space", "ok", "needed", "free", "reason"}` | v0.31.0 |
| `{"type": "offer-stop", "id"}` | `{"type": "offer-stopped", "id"}` | v0.31.0 |
| `{"type": "games-list"}` | `{"type": "games", "games": [{"id": token, "title"}]}` | v0.31.0 |
| `{"type": "pull-check", "game": token}` | `{"type": "pull-size", "title", "bytes", "compatTool"}` | v0.31.0 |
| `{"type": "pull", "game": token}` | `{"type": "pull-started", "game": token}` | v0.31.0 |
| `{"type": "pull-state", "game": token, "state": "failed", "reason"}` | `{"type": "pull-state-received", "game": token}` | v0.31.0 |

- **Who may send them.** `offer-state` and `pull-state` are accepted only about something the receiving device made for, or asked of, the sender. `offer-stop` is accepted only from the device the game came from.
- **Reasons** are one line of at most 300 characters, with any absolute path replaced by "a folder".
- **Tokens** are 16 random hex characters, valid for 15 minutes, for the device they were listed to only, and used once.
- **`offer`** may carry an optional `pull` (a token), tying it to the request it answers.
