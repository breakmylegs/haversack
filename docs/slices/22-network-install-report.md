# Network install (follow-on to slice 22): report

Peter's owner decision (16 November 2026): install from a network location that is not mounted. Decision record: [ADR-0033](../adr/0033-network-install.md).

## What changed

**Backend**
- `keepsake/installer/remote.py` handles HTTP and HTTPS:
  - **Session:** one session per user action, for the typed host and any host the user allowed after a redirect.
  - **Browsing:** listing pages (autoindex style) are read for folders and ISO files one level down.
  - **Downloads:** streamed to staging and resumed with `Range`. The size and optional SHA-256 are checked, there is a space check and a cancel, and the partial file is deleted on failure.
  - **Plain HTTP:** only to local addresses, never with a password.
  - **Remembered locations:** `netlocations.json` (0600) holds the address and user name. Passwords go in the CredentialStore's new keyed secrets (`netinstall-secrets.json`, 0600).
- **`installer/service.py`:**
  - `downloads_dir`;
  - `clean_downloads`, which runs on every Installer start;
  - `start(..., staged=True)` deletes the download when the install ends, or when preparing it fails.
- **`app.py` and `main.py`:** `installer_net_locations`, `remember`, `forget`, `browse`, `download`, `cancel` and `status`, the `keepsake_netinstall_progress` event, and `stagingFree` and `download` in `installer_status`.
- **`scripts/network_mount_probe.py`:**
  - checks the session bus, `gio`, `gdbus`, `busctl`, the gvfsd and gvfsd-fuse helpers, the kio-fuse and gvfs D-Bus service files, running gvfs, kio-fuse and KDE processes, `/dev/fuse`, and staging free space;
  - adds `--loop-test FILE`;
  - prints no paths.

**Frontend**
- Install has a new "From a network location" button, implemented in `NetworkSource.tsx`. It offers:
  - a protocol choice (Web server, SMB, NFS);
  - address, user name, password and "Remember this location";
  - remembered location buttons with Forget;
  - an optional SHA-256;
  - Browse and Up one folder;
  - ISO entries, with a confirmation that shows free space;
  - live progress with the rate and Cancel;
  - a redirect confirmation;
  - a low-space warning.
- SMB and NFS explain what works today.

**Docs:** ADR-0033, T88 to T90, A157 to A160, the changelog, the superseded note on the spike, and the CLAUDE.md allowlist line.

## Tests

- `tests/test_installer_remote.py` (28) runs against a real local `http.server` and a scripted server. It covers:
  - listing;
  - progress;
  - resume after a drop, and a server that ignores `Range`;
  - a resume from the wrong place;
  - checksum, low space and cancel;
  - redirects within the host, to another host and https to http;
  - malformed redirects and too many redirects;
  - credentials sent only to the typed host over https;
  - plain HTTP only on local addresses;
  - address and name checks, and the size cap.
- `tests/test_installer_network.py` (8) covers:
  - deleting a staged ISO when its install ends;
  - a failed start;
  - left-over clean-up;
  - never deleting a path outside the downloads folder;
  - the location store keeping passwords out of its file and out of the page;
  - the app flow: browse, download, then a prepared install;
  - the app refusing another host, reporting redirects, and cancelling;
  - the Installer having to be on.
- `tests/test_fuzz_network.py` (601) feeds random listing pages and addresses. It found that a malformed `[IPv6]` address raised `ValueError` instead of being refused. Fixed in `check_location`, listing parsing and redirect handling, with a regression test.
- `tests/test_network_probe.py` (2): the loop test deletes its loop device, and its output hides paths.
- Existing tests run as regression cover: `tests/test_installer.py` and `tests/test_backends.py`.
- Mutation checks: see the pull request.

## Known gaps

- SMB is not built yet. The recommendation is vendored pysmb (SMB2 only). It is a separate change for the vendoring and hashes.
- WebDAV browsing and SFTP are not built. NFS needs a mount (ADR-0033 explains why).
- Staging uses the plugin's runtime folder on the internal drive. Downloading straight to the SD card library would be a new write location, which is an escalation item.
- `ipaddress` in Decky's frozen Python is unproven. If it is missing, plain http is refused, and https still works.

## Follow-on: WebDAV (17 November 2026)

**What changed**
- `keepsake/installer/webdav.py` maps `davs://` and `dav://` to `https://` and `http://`, so the HTTP rules apply unchanged.
  - `DavSession` lists folders with `PROPFIND` (`Depth: 1`) and downloads with the HTTP `GET` download.
  - Multi-status parsing refuses DTDs, caps the answer at 2 MiB and keeps only children one level down on the same host.
  - A server that answers like a plain web server gets a message pointing to Web server.
- `Session.open` accepts only `GET` and `PROPFIND`.
- Remembered locations keep the `davs://` form.
- The Install page has a WebDAV option, and locations are listed per protocol.
- Docs: ADR-0033 (WebDAV section, status), T93, A163, the changelog.

**Tests**
- `tests/test_installer_webdav.py` (210) runs against a real local server answering `PROPFIND` and `GET`. It covers:
  - address mapping;
  - one-level listing and download;
  - plain errors, and plain web servers told apart;
  - hostile XML;
  - 200 fuzzed `href` sets;
  - the method allowlist;
  - locations, and a password refused over `dav://`;
  - the app flow.
- Mutations: 8 run, 7 caught. The survivor showed a plain web server got an unclear message, which is now explicit and tested.

## On-device checklist

1. Run the probe in both modes from the laptop (PowerShell):
   `Get-Content scripts\network_mount_probe.py | ssh deck@<device> "python3 -"`
2. Desktop Mode: open the NAS share in Dolphin, copy the path of a small ISO on it, then run:
   `Get-Content scripts\network_mount_probe.py | ssh deck@<device> "python3 - --loop-test '<path>'"`
3. Gaming Mode, Install:
   1. Enter a title, then choose From a network location and Web server.
   2. Enter `http://<nas-lan-ip>/<folder>/`, then Browse and choose an ISO.
   3. Watch the progress, then cancel once and check the partial file is gone.
   4. Download again and finish the install.
   5. Check the download is deleted after Done or Cancel.
4. Try an https address with a user name and password and "Remember this location". Leave and come back, and check the location is listed with "password saved".
