# Cloud layout and snapshot schema (frozen)

**Frozen from the merge of slice 6.** Changing anything here afterwards is an escalation item (build prompt section 4) and needs an ADR. New object kinds may be added only in a backwards-compatible way, and readers must ignore what they do not understand.

All paths are inside the backend's app folder (OneDrive: `Apps/Keepsake`). Every object is written once and never modified (principle 2); only retention deletes blobs. Keys use segments of `[A-Za-z0-9][A-Za-z0-9._-]*`.

| Key | Written by | Content |
|---|---|---|
| `registry/devices/<deviceId>.json` | each device, once, after its first sign-in | `{schemaVersion, deviceId, deviceName, registered, pluginVersion}` |
| `games/<gameKey>/snapshots/<snapId>.json` | snapshot publish, after the blob | snapshot metadata, schema 1 (below) |
| `games/<gameKey>/blobs/<snapId>.zip` | snapshot publish, first | zip of `<root>/<rel>` entries |
| `games/<gameKey>/pruned/<snapId>` | retention, before deleting the blob | `{snapId, prunedAt, deviceId}` |
| `games/<gameKey>/pins/<snapId>.json` | pinning (ADR-0007) | `{snapId, until, deviceId, created}`; `until` null means forever |
| `games/<gameKey>/config/<deviceSeq>-<deviceId>.json` | game config revisions (implemented in slice 9, ADR-0020) | `{schemaVersion: 1, gameKey, deviceId, deviceName, seq, created, createdTs, basedOn, config: {aliases, includeConfig, customPaths, exclusions}}`; `deviceSeq` counts this device's revisions for the game; the newest `createdTs` applies |
| `games/<gameKey>/bases/<deviceId>/<deviceSeq>.json` | each device when its base changes (slice 7, ADR-0008) | `{snapId, deviceId, deviceSeq, created}`; the highest `deviceSeq` per device is that device's base |
| `games/<gameKey>/identity/<deviceId>.json` | each device, once, after its first push of the game (ADR-0011) | `{schemaVersion, gameKey, deviceId, title, exe, folders, name, saveDirs, created}`: exe file name, normalised install folder names, normalised shortcut name and `root/folder/folder` save folders, for cross-device matching |
| `games/<gameKey>/prerestore/<snapId>.json` and `.zip` | only if uploading pre-restore snapshots is enabled | as snapshots |

Objects are never empty (OneDrive upload sessions cannot create empty files).

## Snapshot metadata, schema 1

```json
{
  "schemaVersion": 1,
  "snapId": "000042-d3f1a9-9c1e0b7a",
  "gameKey": "goat-simulator-3",
  "parents": ["000041-d3f1a9-77ab01cd"],
  "deviceId": "d3f1a9c2-0000-0000-0000-000000000000",
  "deviceName": "Handheld one",
  "deviceSeq": 42,
  "created": "2026-11-14T13:23:18Z",
  "kind": "auto-exit",
  "flags": [],
  "contentHash": "<sha256 hex>",
  "files": [{"root": "winLocalAppData", "rel": "Goat2/Saved/SaveGames/slot0.sav", "size": 1234, "sha256": "<hex>"}],
  "blobSha256": "<sha256 hex>",
  "pluginVersion": "1.0.0"
}
```

- `snapId` is `<deviceSeq zero-padded to 6>-<first 6 hex digits of deviceId>-<first 8 hex digits of contentHash>`.
- `contentHash` is SHA-256 over one line per file, sorted by root then path: `root NUL rel NUL size NUL sha256 LF`.
- `kind` is one of `auto-exit`, `auto-recovered`, `manual`, `merge`, `import`, `provisional`.
- `root` is one of `winAppData`, `winLocalAppData`, `winLocalAppDataLow`, `winDocuments`, `winSavedGames`, `winPublic`, `winProgramData`, `base`, `home`, `xdgData`, `xdgConfig`, `steamUserdata`, `registry`.
- A plugin never writes to a game whose metadata uses a newer `schemaVersion` than it understands.
- Cloud data never contains absolute device paths, device usernames, compatdata IDs or SD card labels (principle 10). The SteamID64 may appear in a relative path when a game names its save folder after it (assumption A47).
