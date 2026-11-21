# R18 report: three fixes (v0.30.2)

Peter's bug report of 21 November 2026: sending Factorio stalled, OneDrive sign-in ended on a localhost error page, and Find shares and Browse showed Python exceptions. A patch release. The Replication changes requested in the same message (two-way trust, space check, no acceptance, progress and Stop on both sides, toasts) follow as their own minor release.

## 1. Sending a game stalled

### Root cause

- `replication_accept` ran `Incoming.accept` in a worker thread (`asyncio.to_thread`).
- `accept` called `Transfers.start`, which makes each copy an asyncio task. With no event loop in that thread, `create_task` raised `RuntimeError`, which the app did not catch.
- By then the offer was already recorded as "transferring" and each job as known, so the page showed "transferring" with nothing running, for ever.
- A copy that did fail only set a reason and left the state "transferring".
- The sending device was never told anything after the offer, so it said "offered, waiting for the other device".

The same pattern was in `replication_apply_update` (`accept_update`).

### The fix

- **Planning and starting are split.** `Incoming.begin` and `begin_update` check, record and plan the copies, and are safe in a worker thread. `start_jobs` starts the copies on the event loop. The app now calls `begin` in a thread, then `start_jobs` on the loop.
- **A copy that cannot start fails the offer.** `start_jobs` catches the failure and marks the offer **failed** with "the copy could not start: ...". `Transfers.start` also undoes its own record on `RuntimeError`: the job entry, the registry line and the staging folder. Nothing is left listed as running, and the coroutine is closed, not leaked.
- **A failed copy fails the offer.** `job_finished` now sets the state to failed, not only the reason.
- **Both devices know.**
  - Every state change on the receiving device fires `on_state`, as do decline and "Stop and remove". The app then sends an additive `offer-state` request to the sending device, carrying the offer ID, the state and a reason. It tries three times (now, after 5 s, after 30 s).
  - The reason passes through `wire_reason`: it is one line, at most 300 characters, and any absolute path becomes "a folder" (principle 10).
  - The sending device accepts the request only for an offer it made to that same paired device (`Outgoing.record_state`). It shows the state in its list ("copying", "adding to Steam", "arrived", "did not arrive: reason", "declined", "removed"), with a toast when the game failed or arrived.
  - An older Keepsake answers "unknown request". That is logged and nothing more.
- **The sending side no longer hangs on "preparing".** `_send_game` catches every exception, marks the send failed with a reason and shows a toast.
- **Export.** The Device checks' **Export results** adds a `replication` part:
  - incoming offers: the state, reason, size and age, and per copy its state, whether it is running, bytes, held and reason;
  - outgoing offers: the remote state;
  - sends in progress.

  It holds the first 6 characters of each offer ID and no titles, device names or paths.

`offer-state` is a new message type. It is additive: no existing message changes, and an older peer refuses it harmlessly. The peer protocol's existing messages are untouched, so this is not the protocol change that the escalation rules guard.

## 2. OneDrive sign-in ended on a localhost error

### Root cause

The loopback listener closed as soon as the first valid callback arrived, or at once on a cancel. Two cases then hit a closed port:

- **A second load.** The browser loaded the address again (a reload, or a second redirect).
- **A switch to the phone.** The user pressed "Use your phone instead", which cancelled the browser attempt and closed its listener. When Microsoft later redirected that browser tab, nothing answered.

Separately, the `::1` listener was a courtesy: if the port the system gave for `127.0.0.1` was taken on `::1`, Keepsake went without IPv6. A browser that looked up `localhost` as IPv6 then failed.

### The fix

- **A grace period.** After the attempt ends, the listener stays up for 2 minutes (`GRACE_SECONDS`) and answers every request with a page that says how it ended. It never takes a code by then. The pages say:
  - signed in;
  - signed in on your phone;
  - moved to your phone;
  - timed out;
  - did not complete.

  A favicon request gets 204. The listener closes when the grace period ends, and when the plugin stops.
- **Signed in on the phone.** When the phone sign-in succeeds, the app tells each browser attempt the user moved away from (`signed_in_elsewhere`). Their tabs then say "You finished signing in on your phone, so Keepsake is signed in". The sign-in event carries `method`, so the toast says "Signed in with your phone" (Gaming Mode and the desktop page).
- **A failed exchange is not "signed in".** If the token exchange fails, a reload shows the failure page.
- **`::1`.** `_bind_all` holds the same port on every address. If `::1` has that port taken (`EADDRINUSE`), it tries a new port, up to 8 times. A system with no IPv6 still listens on IPv4 alone.

## 3. Find shares and Browse showed Python exceptions

### Reproduction

A probe ran the app's `installer_net_browse` and `installer_net_remember` against the fake share server in `test_installer_smb.py`, with found-server addresses, typed addresses, remembered locations and credentials. No exception escaped the backend untyped: every failure was a `ValueError`. Three problems showed:

- **What the user sees.** Decky rejects a failed call with a `PyError` named `Python ValueError` (decky-loader `wsrouter.ts`, A214). The page showed `String(err)`, so every message read "Python ValueError: ...". For example, picking a server before entering a password showed "Python ValueError: the share refused the user name or password (or needs one)".
- **Windows paths leaked into SMB paths.**
  - `\\NAS\Games` with the SMB protocol became `smb://\\NAS\Games`. Its server name was `\\nas\games`, so it could not be found.
  - `smb://nas/Games\Old` was refused as an invalid folder name.
  - `\\192.168.1.20\Games` could not be remembered at all: it was taken for a web address and refused with "the address starts with http://".

  These are the "pathing" errors.
- **`DOMAIN\user`.** The user name was passed whole with an empty domain, which Windows refuses.

### The fix

- **Windows addresses.** `smbshare.normalise` turns these into `smb://server/share/folder` before the same checks as before:
  - `\\server\share\folder`;
  - `smb:\\server\share`;
  - `smb://\\server\share`;
  - backslashes in the path.

  `smbshare.is_smb` uses it for the app's session choice and for remembered locations.
- **User names.** `smbshare.split_user` turns `DOMAIN\user` into the domain and the user, and `_connect` passes the domain separately. `user@example.com` stays whole, because Microsoft accounts sign in to shares that way.
- **Plain messages.**
  - The Install page shows `plainError(err)` (`src/format.ts`). A `ValueError` shows only its message, as a sentence. Any other error names its type once and points to diagnostics.
  - On the backend, browse, remember and Find shares turn any unexpected exception into a plain `ValueError` that names the step. They log its type only.

## Not done, and why

- **`plainError` covers the Install page only.** The other places that show `String(err)` (about 40) still show "Python ValueError: ...". The change is mechanical, but it touches every page, so it goes in its own small change rather than this patch.
- **Frontend tests.** The repository has no frontend test runner, so `plainError` and `outgoingText` are covered by the type check, the build and the device run.
- **Finding the real Factorio failure.** The stall hid whatever went wrong. With this release, the reason shows on both devices and in the export. Peter's device run (part 4, step 10) will show it if any remains.

## Tests

New files:

- `tests/test_replication_offer_state.py`, 15 tests:
  - the v0.30.1 code path, starting off the loop: now a plain failure with nothing half-started;
  - begin in a thread, start on the loop: copies;
  - a failed copy fails the offer;
  - decline and Stop and remove tell the sender;
  - path-free reasons (7 cases);
  - the sender accepts news only about its own offers to that device;
  - the app accepts on the loop, tells the sender, and its export is redacted;
  - the app shows news, sends a toast and refuses a stranger;
  - any failure while offering shows on the sender.
- `tests/test_signin_grace.py`, 12 tests:
  - extra requests after sign-in get the signed-in page and a 204 for the favicon;
  - the code is exchanged once, however often the browser comes back;
  - a failed exchange is not shown as signed in;
  - the listener closes after the grace period;
  - a cancel says "moved", then "signed in on your phone";
  - a code that came after the user moved on;
  - a time-out page;
  - IPv6 sign-in, when the system has `::1`;
  - a port taken on IPv6 means another port;
  - no IPv6 still listens on IPv4;
  - the app tells an open tab when the phone sign-in worked, and the listener goes with the plugin;
  - a cancel is still a cancel.
- `tests/test_smb_find_regressions.py`, 19 tests:
  - Windows addresses (7 cases);
  - backslashes never reach a name;
  - domain user names (6 cases);
  - `_connect` sends the domain separately;
  - picking a found server lists its shares, or says plainly why not;
  - a remembered Windows location with credentials browses;
  - a typed Windows address browses;
  - an unexpected fault is a plain message.

Changed regression tests:

- `tests/test_loopback_auth.py`: two tests now expect the grace page, then a closed listener after `close()`.
- `tests/test_replication_ongoing.py`: the both-sides test stubs `begin_update`.

Regression tests run, named:

- `tests/test_replication_sendgame.py`
- `tests/test_replication_ongoing.py`
- `tests/test_replication_transfers.py`
- `tests/test_loopback_auth.py`
- `tests/test_auth.py`
- `tests/test_installer_smb.py`

All pass. 3 are skipped on Windows (symlinks, a Unix socket, POSIX file modes).

Mutation tests, each proven by breaking the code its tests guard:

- **Offers, transfers and the app (16 mutations):** all caught. They covered starting in a thread, the caught `RuntimeError`, the failed state, the peer check, path redaction, the length cap, each state notice, the redacted export, the toast, the broad catch while sending and the cleanup in `Transfers.start`.
- **Sign-in (15 mutations):** all but one caught. Removing the timer cancel in `close()` survives because it changes nothing visible: `close()` is safe to call twice, so the timer firing later does no harm. One survivor exposed a redundant guard, which was removed; a new test covers that path.
- **SMB (12 mutations):** all caught. They covered each prefix, backslashes in paths, normalising in `parse`, the domain split, sending the domain, the app's and the location store's SMB detection, and the plain messages. One survivor showed that normalising before building `Share` was redundant (`Share` parses), so it was removed. Another led to the typed `\\server\share` test.

The gate (`python scripts/check.py`) result is in the pull request.

## Threat model and assumptions

- **Threat model:**
  - T132: offer states on both devices, with redacted reasons and peer checks;
  - T133: the sign-in listener's grace period;
  - T134: Windows-style share addresses and user names.
- **Assumptions:**
  - A214, verified: Decky's `PyError` name and message;
  - A215: pysmb takes the domain separately (verified from source; Windows behaviour unverified);
  - A216: browser reloads and late redirects (unverified, the device run checks it).

## On-device checklist

In `docs/device-run.md`, part 4:

- **Step 10:** sending a game, both sides, a failure on both, and the export.
- **Step 11:** OneDrive sign-in, a reload, and finishing on the phone.
- **Step 12:** Find shares, a Windows-style address and user name, and the remembered location.
