# ADR-0055: The built-in sign-in clients' values, and the Google secrets kept out of the repository

- Status: accepted (18 November 2026; decided under ADR-0037)
- Date: 18 November 2026
- Deciders: Peter (owner)
- Amends: ADR-0032 (where the Google secrets live)

## Context

Peter registered Keepsake's built-in clients on 18 November 2026, under accounts made only for Keepsake (option A, ADR-0054):
- one Microsoft Entra app for personal accounts;
- two Google OAuth clients in one project: "Desktop app" for the browser sign-in and "TVs and Limited Input devices" for the phone sign-in.

ADR-0032 planned to commit all of these values in `keepsake/clients.py`. Client IDs are public identifiers, so that holds for them.

The Google client secrets are another matter, even though Google says these client types "cannot keep secrets":
- **The in-repository scan blocks them.** `scripts/secret_scan.py` flags the `GOCSPX-` shape (T11), the pre-commit hook would refuse them, and the working rules forbid circumventing it.
- **GitHub scans public pushes for secrets.** Its push protection and secret scanning look for Google OAuth client secrets, and a reported secret may be revoked by its provider.

## Decision

1. **Client IDs are committed.**
   - `ONEDRIVE_CLIENT_ID`, `GOOGLE_CLIENT_ID` (TV client) and `GOOGLE_DESKTOP_CLIENT_ID` are in `clients.py`.
   - Release builds sign in with one button and need no client ID.
2. **Google secrets ship only in the packages.**
   - **Where they live:** the two secrets are in `py_modules/keepsake/client_secrets.json`, which is git-ignored and kept on the release laptop.
   - **Packaging:** the existing walk over `py_modules` puts the file in both packages, the plugin zip and the PC zip. Those are signed through `SHA256SUMS` as before.
   - **Reading:** `clients.py` reads the file at import, and accepts only `GOCSPX-` values.
   - **Without the file:** in a source checkout, the Google built-in clients count as absent, as before. Each one has an ID but no secret, so it is treated as no client at all and the user's own client is asked for.
3. **A release cannot forget them.**
   - `release.py publish` refuses to publish when the file is missing, is not JSON, or lacks either secret.
   - A dry run warns.
   - `docs/releasing.md` says how to recreate the file on another laptop.
4. **This is not hiding a secret.** The values are public in every release, as Google intends for installed apps. The change only keeps a scanner-shaped string out of git history, so no scanner is bypassed: nothing flagged is committed.
5. **The setup pages are rewritten** with the steps Peter followed (`docs/setup-entra.md`, `docs/setup-google.md`). They are now for people who want their own registration, under Advanced.

## Consequences

- **Tests:** they no longer depend on whether the laptop has the file. The built-in-client tests set every value they rely on.
- **T113 and A189:**
  - T113: a leaked or reused built-in client;
  - A189: GitHub does not scan release assets, and Google does not disable an installed app's secret that appears in a public download.
- **If Google ever disables a secret:**
  1. make a new secret for the same client;
  2. update the local file;
  3. release again.

  Existing sign-ins keep refreshing only if Google allows it, so A189 is watched.

## Sources

- Google, [OAuth 2.0 for iOS and Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app): installed apps "cannot keep secrets".
- Google, [OAuth 2.0 for TV and Limited-Input Device Applications](https://developers.google.com/identity/protocols/oauth2/limited-input-device).
- GitHub, [Supported secret scanning patterns](https://docs.github.com/en/code-security/secret-scanning/introduction/supported-secret-scanning-patterns) (Google OAuth client secrets).
