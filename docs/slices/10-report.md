# Slice 10 report: additional backends and Ludusavi import

Branch `slice/10-backends-import`, stacked on `slice/09-gaming-mode-ux` (#11). Build prompt slice 10: WebDAV, S3 and Google Drive stores, and a Ludusavi importer that writes `import` snapshots. Design decisions: ADR-0021 (items 3 and 6 flagged for Peter).

## What changed

**Backend**
- `store/webdav.py`, `store/s3.py` (with `store/sigv4.py`), `store/gdrive.py`, sharing `store/httpcall.py` (retries, a DTD-refusing XML parser, upload helpers).
- `auth.py`: a `Provider` description; Google's device flow with the `drive.appdata` scope and the user's client secret. OneDrive unchanged.
- `net.py`: Google-only transport and a single-host, HTTPS-only transport for user endpoints.
- `backends.py` (new): WebDAV, S3 and Google client settings, mode 0600, secrets never returned.
- `importers/ludusavi.py` (new): reads `mapping.yaml`, full and differential backups, simple and zip formats; maps absolute paths to logical roots by shape; verifies size and SHA-1.
- `retention.py`: `import` snapshots are never heads. `engine.py`: `take` accepts the original creation time.
- `app.py`: backend choice and checks (`test_cloud` proves create-only writes for WebDAV and S3 and registers the device), Google sign-in, backend settings, `ludusavi_scan` and `ludusavi_import` (staging in the runtime folder, duplicate detection, a job so updates wait); health and sign-in toasts name the backend in use.
- `settings.py`: `snapshotStore` accepts `webdav`, `s3`, `gdrive`. `main.py`: the new callables.

**Frontend**
- Settings, Cloud: choose the test store, OneDrive, Google Drive, WebDAV or S3; forms with the on-screen keyboard (secrets as password fields, "Saved. Leave empty to keep it."); sign-in with QR code for OneDrive and Google; a backend is switched on only after its check passes.
- Import tab: read a Ludusavi folder (typed path or file picker), see each game's backups, game key and whether it is on this device, then "Import latest" or "Import all".
- The QAM names the backend in use.

**Docs**: ADR-0021, `docs/setup-google.md`, `docs/setup-backends.md`, threat model T61 to T67, assumptions A111 to A117, cloud layout notes on imports and backends, CHANGELOG 0.10.0.

## Tests

- New: `fake_clouds.py` (fake WebDAV, S3 and Drive servers), `test_cloud_stores.py` (17, including AWS's two published SigV4 example signatures), `test_ludusavi.py` (27), `test_backends.py` (11), `test_app_backends.py` (5). The store contract (`test_store_contract.py`) now runs every test against all five backends (65). It now allows a store to report no upload hash (WebDAV), never a wrong one.
- The contract found one real bug during development: S3 listing went to the prefix path instead of the bucket.
- Re-run because they cover touched code: `test_health.py`, `test_auth.py`, `test_app_cloud.py`, `test_graph_store.py`, `test_app_ux.py`, `test_settings.py`, `test_net.py`, `test_gates_retention.py`, `test_engine.py`, `test_sync.py`, `test_sync_invariant.py`, `test_sync_plan.py`, `test_app_snapshots.py`, `test_app_sync.py`, `test_identity.py`, `test_yamlsubset.py`. Two failed on wording I had changed (the OneDrive sign-in error and a health detail); the first was fixed in the code, the second in the test.
- Mutation checks: 25 guards broken one at a time:
  - create-only on WebDAV and S3, and both create-only proofs;
  - S3 delete of a missing key and S3 pagination;
  - SigV4 query ordering;
  - Drive's oldest-wins rule, losing-copy deletion, name pre-check and redirect refusal;
  - the XML DTD refusal and imports excluded from heads;
  - path validation, hash checks, differential removals and prefix detection in the importer;
  - duplicate-import and game key checks;
  - keeping blank secrets, HTTPS only and hiding secrets;
  - the Google client secret and refresh scope, device registration and the single-host transport.

  The first run missed three: query ordering (AWS's example query was already sorted), Drive's losing-copy deletion (the test never reached the race path) and Drive's pre-check (only saves an upload). Tests were added and all 25 are now caught.
- `python scripts/check.py`: all checks pass (eslint, tsc, build, versions, package, ruff, ruff format, mypy, secret scan).

## Known gaps

- Uploads to WebDAV, S3 and Drive are single requests of up to 1 GiB; save blobs are far smaller. Resumable uploads can follow if needed.
- Drive listing reads the whole app folder and filters locally; fine for thousands of objects.
- Ludusavi registry backups (`registry.yaml`, Windows only) are not imported; Proton `*.reg` files are, as ordinary files. Paths inside a game's own install folder are skipped, because their place on the other device is not known.
- Importing from Ludusavi's OneDrive copy would need a broader OneDrive scope (escalation), so only a local folder is read.

## On-device checklist

1. Google Drive: create credentials per `docs/setup-google.md`, sign in from Settings with the phone, Test connection, use it, then play and quit a synced game: a snapshot appears in History.
2. If you have a WebDAV or S3 account, set it up per `docs/setup-backends.md`; Test connection must pass before "Use ... for snapshots" works.
3. Import: open the Import tab, read `~/ludusavi-backup` (or choose the folder), and "Import all" for at least three games. History shows the imported snapshots with their Ludusavi dates; nothing changes on the device.
4. On the other device, open each of those games and restore an imported snapshot from History; the game loads that save. Undo is available on the game page.
5. Run `pnpm run test:device` (includes the symlink and file mode tests skipped on Windows).
