# ADR-0021: WebDAV, S3 and Google Drive stores, and the Ludusavi import

- Status: accepted (slice 10, decided under Peter's delegation; items 3 and 6 flagged for his review)
- Date: 15 November 2026
- Deciders: Peter (owner)
- Sources: build prompt sections 6, 9, 11, 16 (slice 10) and 19; `docs/build-prompt-v2.md` section 10

## Context

Slice 10 adds three backends behind the existing store contract and an importer for Peter's interim Ludusavi backups. Every store must be write-once (principle 2) with an atomic create-only write (threat model T13). Ludusavi stores files by absolute path, including the old compatdata number, which differs per device.

## Decision

1. **One contract, five stores.** WebDAV, S3 and Google Drive implement `Store` and pass the same contract tests as the local folder and OneDrive. Shared retry rules live in `store/httpcall.py`.
2. **WebDAV and S3: create-only through `If-None-Match: *`, proven before use.** Some servers ignore the header. "Test connection" (and switching to the backend) writes `registry/probe/<deviceId>.json` once and then tries to write it again; the backend is refused unless the second write is rejected (fail closed). The probe is a few bytes and is kept. Only HTTPS endpoints are accepted, and the transport for a user-configured endpoint reaches only that one host (`net.endpoint_transport`).
3. **Google Drive: create-only built on top.** Drive allows duplicate names and has no conditional create. The store checks the name is free, uploads, then lists every file with that name; the oldest by Drive's own `createdTime` (then file ID) is the object. A writer that finds an older copy deletes the copy it has just made and reports "already exists". Readers apply the same rule, so racing devices agree. This deletes a file outside retention, but only a writer's own losing duplicate seconds after creating it, never anything another device could have relied on. Flagged for Peter because it touches the "deleting cloud data outside retention" escalation rule. In practice keys are device-specific (snapshot IDs, per-device records), so collisions come only from retries.
4. **Google sign-in** uses the device flow for limited-input devices with scope `drive.appdata` (the narrowest Drive scope Google allows for this flow, verified on Google's documentation page on 15 November 2026). Files live in the hidden app data folder. The client ID and secret are the user's own, entered in Settings and stored mode 0600; they are never committed. `auth.py` is generalised with a `Provider` description; OneDrive behaviour is unchanged.
5. **Integrity.** S3 uploads carry a SigV4-signed payload hash that the service checks, so success means the bytes arrived intact. Drive reports `sha256Checksum`. WebDAV reports nothing, so its uploads return no hash and the snapshot engine verifies by download (the contract allows `None`, never a wrong hash). XML answers are parsed with the standard library after refusing any DTD or entity declaration.
6. **Ludusavi import creates `import` snapshots that are never heads.** An old backup imported as a head would raise a fork conflict on every device or replace current saves. Imports are therefore excluded from the DAG's heads (`retention.heads`), kept forever by retention (as before), shown in History with their original dates, and restored by hand with the normal pre-restore snapshot. This is a rule about an existing snapshot kind; the frozen layout is unchanged, but devices on an older version would treat imports as heads, so both devices should update before importing. Flagged for Peter as a snapshot semantics change before slice 6 merges.
7. **Import source and mapping.** The import reads a Ludusavi backup folder on the device (default `~/ludusavi-backup`, or chosen with the file picker); it never writes there. Reading Ludusavi backups from elsewhere in OneDrive would need a scope beyond `Files.ReadWrite.AppFolder`, an escalation item (v2 section 10), so it is not offered. Absolute paths are mapped by shape: `.../pfx/drive_c/users/steamuser/AppData/...` in any prefix, `Documents`, `Saved Games`, `users/Public`, `ProgramData`, Windows `C:/Users/<name>/...`, Linux home, XDG folders and Steam `userdata`. Anything else is listed as skipped. Every file is checked against Ludusavi's recorded size and SHA-1, and a mismatch or missing file refuses that backup. Differential backups apply their changes and removals over the full backup. Importing the same backup twice is detected by content hash and date.
8. **Game key.** The Ludusavi game name is a manifest title, so the import uses `manifest.game_key(name)`, the key the manifest match gives on every device; the page says whether the game is on this device.

## Consequences

- Peter's acceptance item (three games imported and restored on the other device) is an on-device check.
- `docs/setup-google.md` and `docs/setup-backends.md` explain the Google project and the WebDAV and S3 settings.
- Mixed-version devices see imports as heads until updated (item 6).
