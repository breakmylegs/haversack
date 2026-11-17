# S1 report: one-button cloud sign-in

Peter's requirement of 17 November 2026, recorded in ADR-0044.

## What changed

- **Browser sign-in** (`keepsake/loopback_auth.py`): authorization code with PKCE (S256) and an RFC 8252 loopback redirect.
  - **The listener:** one-shot, on 127.0.0.1 (plus `[::1]` for Microsoft's `localhost`), on a port the system picks.
  - **The callback:** `state` is checked in constant time.
  - **Closing:** after the first valid answer, a cancel or 5 minutes.
  - **The exchange:** tokens are stored and refreshed exactly as with the device code flow.
- **Providers:**
  - Microsoft: `http://localhost:<port>`, `/consumers`, same scopes.
  - Google: `http://127.0.0.1:<port>`, `access_type=offline` and `prompt=consent`, so every sign-in returns a refresh token.
  - Google uses a second built-in client, "Desktop app" (`GOOGLE_DESKTOP_CLIENT_ID`). Its "TVs" client stays for the phone sign-in.
- **`start_signin(backend, method)`:** "browser" or "phone". It defaults to "phone", so older callers are unchanged.
  - **`cloud_status().methods`:** says which methods have a client.
  - **New setting `gamingModeSignin`:** OneDrive defaults to the browser, Google to the phone.
- **Gaming Mode:**
  - **Buttons:** "Sign in with OneDrive" and "Sign in with Google" open Steam's browser (`Navigation.NavigateToExternalWeb`). Focus returns to the button afterwards.
  - **Switch:** "Sign in with this device's browser", with a one-line reason when the phone is used.
  - **Fallback:** "Use your phone instead" appears after a browser attempt fails.
- **PC desktop interface:** a Cloud page with "Sign in with ..." (the default browser in a new tab), Sign out and "Use ... for snapshots".
- **Diagnostics, "Sign-in browser test":** loopback reachability, Microsoft and Google in Steam's browser. The outcomes go to the diagnostics export.
- **Docs:** ADR-0044 (with the shortest registration steps and the per-device sign-in decision), ADR-0032 amended, `setup-entra.md` and `setup-google.md`, T101, A172 to A175 and the changelog.

## Test results

- `tests/test_loopback_auth.py` (16), `tests/test_builtin_clients.py`, `tests/test_app_cloud.py`, `tests/test_settings.py`, `tests/test_auth.py` and `tests/test_host.py`: all pass. Two POSIX-only tests are skipped on Windows.
- Mutation checks: 23 mutations, all killed after two tests were added for the first-round survivors.
- Quality gate: see the pull request.

## Known gaps

- No real sign-in until the client IDs arrive. Microsoft's `localhost` matching and Google's Desktop loopback are tested only against a fake token endpoint (A172).
- The Gaming Mode defaults are assumptions until the probe run (A174), and so is the focus restore (A175).
- The setup wizard's cloud step uses the same `CloudSection`, so it gains the browser sign-in too. No separate wizard change is needed.

## On-device checklist (Legion Go 2): the sign-in browser probe

1. **Install the build.** From the repository on the laptop:
   ```
   npx -y pnpm@9.15.9 run build
   python scripts/deploy.py
   ```
2. **Open the probe.** In Gaming Mode, open Keepsake, then Settings, then Diagnostics. Scroll to **Sign-in browser test**.
3. **Step 1, Loopback.** Press **Open the test page**.
   - Steam's browser should show "You're signed in". Press B to come back.
   - Press **Check**, and note `arrived`, `address` and `userAgent`.
   - Then note whether the controller still moves focus on the page without touching the screen.
4. **Step 2, Microsoft.** Press **Open Microsoft sign-in**, sign in with your Microsoft account, come back, and press the button that matches what happened.
5. **Step 3, Google.** The same with **Open Google sign-in**.
6. **Export.** Press **Export diagnostics**. The file name appears on screen. Copy it to the laptop, using the address you deploy to:
   ```
   scp deck@<device-address>:~/homebrew/settings/Keepsake/diagnostics-*.json tmp/
   ```
   Then send me the three outcomes from the screen, or the `probeEvents` part of that file.
7. **Optional, Desktop Mode.** Repeat steps 3 to 5 in Desktop Mode.
