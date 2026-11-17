# ADR-0039: The PC host and its loopback API

- Status: accepted (decided under ADR-0037; P2 of ADR-0038)
- Date: 17 November 2026
- Deciders: Peter (owner)

## Context

On a PC there is no Decky. `python -m keepsake.host` runs the same `KeepsakeApp` and must serve the desktop UI and an API to the browser. That API can restore saves, sign out of the cloud and change settings, so it must be reachable only by the user's own browser tab, never by another web page or another machine.

## Decision

1. **Folders.** The host keeps settings, state and logs in the platform's own places, never inside the program folder:
   - Windows: `%APPDATA%\Keepsake\settings`, `%LOCALAPPDATA%\Keepsake\runtime` and `\logs`.
   - Linux: `$XDG_CONFIG_HOME/keepsake/settings`, `$XDG_STATE_HOME/keepsake/runtime` and `/logs`.

   This is the PC part of the write allowlist (ADR-0038). The save folders written are the same logical roots as on handhelds.
2. **Bound to `127.0.0.1` only.**
   - **Port:** 47120 by default, then the next nine ports if one is taken. These are clear of 8080, 8384, 27040, 1714 to 1764 and Replication's 47110.
   - **The port is owned outright.** `http.server`'s `ThreadingHTTPServer` sets `SO_REUSEADDR`. On Windows that lets a second socket bind a port already in use and take its traffic, which `tests/test_host.py` caught on this laptop. The host turns reuse off and sets `SO_EXCLUSIVEADDRUSE` on Windows (A167).
3. **Who may call.**
   - **`Host` header:** must be `127.0.0.1:<port>` or `localhost:<port>`. A page that rebinds its own domain to 127.0.0.1 is answered 421 (DNS rebinding).
   - **`Origin`:** if present, it must be the host's own. Other sites get 403 (CSRF).
   - **Token:** every call carries the per-run token, 256 random bits, in `X-Keepsake-Token`, compared in constant time.
     - **Event stream:** `EventSource` cannot send headers, so the token travels in the query string of `/api/events`. That address is never logged or linked, and is sent with `Referrer-Policy: no-referrer`.
     - **The UI** gets the token from the URL fragment (`#token=`), which browsers never send to a server.
   - **Calls:** only the callables the Decky plugin exposes in `main.py`. `tests/test_host.py` checks the two lists match.
4. **Requests and answers.**
   - **Requests:** JSON only (415 otherwise), bodies capped at 1 MiB (413). The body is read before any refusal, so Windows does not reset the connection (A168).
   - **Errors:** a `ValueError` or `TypeError` from the app returns its plain message. Any other exception returns only its class name, so no path or detail reaches the page.
   - **Logging:** requests are never logged (T11).
   - **Headers:** `Cache-Control: no-store`, `nosniff`, `X-Frame-Options: DENY`, and a CSP of `default-src 'self'; frame-ancestors 'none'`.
5. **Finding the host.** The port and token are written to `host.json` in the runtime folder, so the launcher can open `http://127.0.0.1:<port>/#token=...`. The folder is the user's own, and another user on the machine cannot read it.

## Consequences

- Any process running as the same user can read `host.json` and call the API. That is the same trust as the user's own files, and those processes could read the saves directly anyway.
- The desktop UI (P3) is a static page served by the host, with no third-party origins.
