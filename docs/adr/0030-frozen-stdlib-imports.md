# ADR-0030: Lazy imports for stdlib modules Decky's frozen Python may not bundle

- Status: accepted (16 November 2026, bug fix requested by Peter)
- Deciders: Peter (owner)
- Sources: Peter's report from his Legion Go 2 (`ModuleNotFoundError: No module named 'xml.etree'` in Decky's journal); Decky Loader `backend/pyinstaller.spec` and `backend/**/*.py` on `main`, read through the GitHub API on 16 November 2026

## Context

On Peter's Legion Go 2, Keepsake's backend did not start at all. `main.py` imports `keepsake.app`. That imports the Google Drive, S3 and WebDAV stores, and `store/httpcall.py` imported `xml.etree.ElementTree` at module level. Decky's Python there has no `xml`, so the whole import failed. Every backend call then hung: Updates stayed on "Checking", and Games, the manifest update and shortcuts all failed.

Decky Loader ships a frozen interpreter built by PyInstaller from `backend/pyinstaller.spec`. PyInstaller bundles only the modules reachable from the loader's own code, plus the spec's `hiddenimports`: `logging.handlers`, `sqlite3`, `http.server`, `socketserver` and `configparser`. Nothing in the loader imports `xml`.

## Decision

1. **Evidence, not guesses.**
   - The loader's backend (20 files) imports these stdlib modules directly: `asyncio` (with `exceptions` and `subprocess`), `enum`, `grp`, `hashlib`, `importlib.metadata`, `importlib.util`, `io`, `json`, `logging`, `mimetypes`, `multiprocessing`, `os`, `pathlib`, `platform`, `pwd`, `random`, `re`, `shutil`, `signal`, `ssl`, `stat`, `subprocess`, `sys`, `time`, `traceback`, `typing`, `urllib.parse`, `uuid` and `zipfile`.
   - Their transitive closure, computed with `modulefinder` together with the hiddenimports, has 381 modules. It is a lower bound: aiohttp, jinja2 and watchdog bring in more.
   - Keepsake's stdlib imports outside that closure are `xml.etree.ElementTree`, `resource` and `tomllib`.
2. **Each of those is imported only inside the feature that needs it**, and fails gracefully:
   - `xml`, in `httpcall.parse_xml` (WebDAV and S3 listings). Without it, a `StoreError` says WebDAV and S3 are not supported by this Decky build. Choosing either is refused with the same message. OneDrive, Google Drive and the local store need no XML.
   - `resource` was already lazy (memory figure for the manifest), and `sqlite3` already had a fallback.
   - `tomllib` is used by the Advisor's lsfg-vk reader (slice 15, not yet merged). It is made lazy there, and the lsfg-vk values are then simply not shown.
3. **Reported in plain words.**
   - Diagnostics list `xml`, `tomllib` and `resource` with `sqlite3`.
   - A health check, "Python modules in this Decky build", warns, and fails if WebDAV or S3 is the chosen cloud without `xml`.
4. **Guarded by a test.** `tests/test_frozen_stdlib.py` runs `main.py` in a fresh interpreter with `xml`, `tomllib` and `resource` blocked by a `sys.meta_path` finder. It starts and stops the plugin and checks that the health check, the diagnostics and the WebDAV refusal all report the gap. Putting the top-level import back makes it fail with the device's error. Any future module outside the closure should join its blocked list.
5. **Patch release v0.22.1.**

## Consequences

- WebDAV and S3 are unavailable on Decky builds without `xml`. A stdlib-only XML reader would avoid that, but writing one is not worth the risk while OneDrive and Google Drive work.
- The closure is a lower bound, so the set of "not proven bundled" modules may include some a real build has. Treating them as optional costs nothing.
