# ADR-0008: OneDrive sign-in and Graph store

- Status: accepted (decided in slice 6 under the owner's delegation, 15 November 2026)
- Date: 15 November 2026
- Deciders: Peter (owner)

## Context

Slice 6 adds the OneDrive backend: device code sign-in, token refresh, a create-only store in the app folder, upload sessions and hash verification (build prompt section 11). Microsoft's current documentation was read for the device code flow, upload sessions, simple uploads and the app folder (assumptions A52 to A58).

## Decisions

1. **Sign-in.** Device code flow against `login.microsoftonline.com/consumers`, scopes `Files.ReadWrite.AppFolder offline_access` only. `authorization_pending` keeps polling at the server's interval; `slow_down` adds 5 seconds (RFC 8628); `authorization_declined`, `expired_token` and `bad_verification_code` stop. The verification page must be HTTPS on `microsoft.com` or `live.com`, else sign-in is refused (T2).
2. **Tokens.** One file, `onedrive-token.json`, mode 0600, in the settings folder. Refreshed when less than 5 minutes remain; a returned refresh token replaces the old one, otherwise the old one is kept. `invalid_grant` or `interaction_required` mean "sign in again"; offline is not a sign-in problem.
3. **Client ID.** A setting entered on the device (`docs/setup-entra.md`). A public client ID is not a secret and may be committed later as a default.
4. **Create-only writes use upload sessions for every object.** The Graph page for simple uploads no longer documents a create-only option; upload sessions document `conflictBehavior: fail` (the default) and a 409 `nameAlreadyExists` when the final range lands on a taken name. A conflict cancels the session. Chunks are 10 MiB (a multiple of 320 KiB, as required). Because upload sessions cannot create empty files, every cloud object has content (the `pruned/` marker became a small JSON object).
5. **Network allowlist addition (escalation item, decided under delegation).** Upload URLs and download redirects for OneDrive personal point at Microsoft content hosts, not `graph.microsoft.com`. Allowed: hosts ending in `.1drv.com` and `.microsoftpersonalcontent.com`, only through URLs Graph returns, HTTPS only, with dot-boundary matching. The bearer token is never sent to them: the Graph documentation warns against it for upload URLs, and download redirects are followed by hand instead of by `urllib` (which would forward headers).
6. **Verification.** After an upload, the hash OneDrive reports is compared: SHA-256 if present, else QuickXorHash (implemented in `keepsake/quickxor.py` from Microsoft's published algorithm). If neither matches or none is reported, the engine downloads the object and compares SHA-256. An error in the QuickXorHash code can therefore cost a download, never accept a bad upload.
7. **Retries.** 401 refreshes the token once; 429 and 5xx back off (honouring `Retry-After`, capped at 30 seconds, four attempts); a disallowed host is never retried.
8. **Device registry.** `registry/devices/<deviceId>.json` is written once after the first sign-in. Name changes show in snapshot metadata (`deviceName`) instead of rewriting the entry.
9. **Device bases (layout addition before the freeze).** `games/<gameKey>/bases/<deviceId>/<deviceSeq>.json`, write-once; the highest sequence per device is that device's base. Retention (slice 7 onwards) protects it. Added now because the layout freezes when this slice merges (`docs/cloud-layout.md`).
10. **Live contract test.** Opt-in, using the token Keepsake stored on the device (`scripts/test_on_device.py --onedrive`). It works only under `contract-tests/<random>/` and deletes what it created. That deletion is of test data, not user data, so it is outside the "deletion outside retention" escalation rule.
11. **Store choice.** Until the sync engine (slice 7), the game page snapshot panel uses the local test store unless "Use OneDrive for snapshots" is switched on in Settings.

## Consequences

- The plugin can reach two more Microsoft host families, but only as directed by Graph and without credentials.
- Small objects take two requests (create session, upload). Acceptable for metadata-sized writes.
- The cloud layout and snapshot schema are frozen from this merge (`docs/cloud-layout.md`).
