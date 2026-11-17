# ADR-0044: One-button cloud sign-in

- Status: accepted (Peter's requirement, 17 November 2026; details decided under ADR-0037)
- Date: 17 November 2026
- Deciders: Peter (owner)

## Context

Peter wants cloud sign-in to work like this:

1. Press "Sign in with OneDrive" (or Google).
2. A browser opens. He signs in with his normal account and allows access.
3. From then on Keepsake just works.

Users never see a client ID; that field stays under Advanced. Tokens refresh silently, and he is asked again only when the provider revokes access.

Until now, sign-in was the device code flow only (ADR-0008, ADR-0021): a code and a QR to scan on a phone. ADR-0032 added built-in clients, whose IDs are still waiting on Peter's registrations.

## What the primary sources say

- **RFC 8252 (OAuth 2.0 for Native Apps).**
  - Section 7.3: loopback redirects use `http` with an IP literal and the port the app listens on. The authorization server "MUST allow any port to be specified at the time of the request".
  - Section 8.3: open the port only when starting the request, and listen only on the loopback interface. "localhost" is NOT RECOMMENDED.
  - Section 8.12: native apps "MUST NOT use embedded user-agents".
- **Microsoft (Redirect URI best practices, updated 2026).**
  - `http` is allowed only for localhost, and the port is ignored when matching localhost redirects. The path is matched and case-sensitive.
  - `[::1]` is not supported.
  - Microsoft prefers `127.0.0.1`. The portal's Redirect URIs box refuses an `http://127.0.0.1` redirect, so that needs a manifest edit (`replyUrlsWithType`).
  - Apps that sign in personal accounts may not have query parameters in redirect URIs.
- **Google (OAuth 2.0 for iOS and Desktop Apps).**
  - Client type "Desktop app". The listener is on the loopback IP and a random port; `localhost` works but "may cause issues with client firewalls".
  - Always use PKCE, with S256 recommended.
  - Desktop apps are public clients that "cannot keep secrets", so the client secret is not treated as a secret.
  - Endpoints: `https://accounts.google.com/o/oauth2/v2/auth` and `https://oauth2.googleapis.com/token`.
  - `disallowed_useragent` is shown when the page is in an embedded user agent.
- **Google Developers Blog, June 2021.** Embedded webviews have been blocked since 30 September 2021. Adding `disallow_webview=true` to the authorization address shows whether a browser is treated as embedded.
- **`@decky/ui` 4.16.5 (in `node_modules`).** `Navigation.NavigateToExternalWeb(url: string): void` exists. Keepsake already uses it in Advisor.
- **DeckyHub PR #156.** After returning from Steam's browser, gamepad focus is left on an invisible panel and the page re-mounts. The fix records the focused control before opening the browser and focuses it again on return.

## Decision

1. **The flow.** Authorization code with PKCE (S256, a 64-byte random verifier) and a loopback redirect, in a new `auth.LoopbackFlow`:
   - **The listener:** a one-shot HTTP listener on `127.0.0.1` with a port the system picks. It opens when the user presses Sign in and closes after the first valid callback, a cancel, or 5 minutes.
   - **The callback:** only `GET /` with `state` and either `code` or `error` is accepted. `state` is 32 random bytes, compared in constant time. Anything else gets a 404 and does not end the attempt.
   - **The page:** the browser is shown "You're signed in. You can close this tab." or a plain failure page.
   - **The exchange:** `code`, `code_verifier` and `redirect_uri` (with the client secret for Google) go to the existing token endpoint. Tokens are stored and refreshed exactly as today (`TokenStore`, `TokenManager`).
   - **Redirect addresses:**
     - Microsoft: `http://localhost:<port>`. It is the address the portal accepts with no manifest edit, which keeps Peter's registration to two fields, and the port is ignored when matching. Keepsake listens on `127.0.0.1` and also on `[::1]` where the system has it, so a browser that resolves `localhost` to IPv6 still arrives.
     - Google: `http://127.0.0.1:<port>`, as Google and RFC 8252 recommend.
2. **Which browser.**
   - **PC host:** the system default browser. The desktop page opens the provider's address in a new tab.
   - **Decky, Gaming Mode and Desktop Mode:** Steam's browser, through `Navigation.NavigateToExternalWeb`. Focus is restored to the Sign in button on return, as DeckyHub's fix does.
   - **Checks:** before opening, the backend checks that the address is `https://login.microsoftonline.com/consumers/...` or `https://accounts.google.com/...`. The frontend opens only what the backend returns.
3. **A fallback for each provider in Gaming Mode.**
   - **The setting:** each provider has one, "Sign in with": "This device's browser" or "Your phone (QR code)". "Your phone" is the existing device code flow, kept unchanged.
   - **Defaults until Peter's probe reports:**
     - Microsoft: the browser;
     - Google: the phone, because Google blocks embedded browsers by policy and users report the block in Steam's browser.
   - **The reason is shown:** one line says why, for example "Google does not allow sign-in inside Steam's browser, so use your phone."
   - **Changing the defaults:** the probe's results set them in a later change. The setting stays so a user can switch either way.
   - **Fallback after a failure:** a browser attempt that fails or times out offers "Use your phone instead".
4. **One sign-in for all devices: each device signs in for itself.**
   - **The choice:** every device runs the same one-tap sign-in and holds its own refresh token. The other option was for a signed-in device to enrol another over the paired Replication channel.
   - **Revocation:** a lost device can be revoked alone, at the provider or by signing out, without signing out the rest.
   - **No token moves:** a refresh token never leaves the device it was issued to. This keeps T2 and principle 10 simple: no cloud object or peer message ever holds a credential.
   - **The provider sees each device:** Microsoft and Google record each sign-in separately, so their security pages show each device.
   - **Enrolment was rejected:** copying a token to a peer turns one stolen peer key into every account's token. It would also need a new message type in a protocol frozen after slice 18.
   - **It still feels like "sign in once":** after the first device, each new device shows a single "Sign in with OneDrive" button, and the browser already holds the provider session, so it is usually one tap on "Accept".
5. **Client IDs only under Advanced.** The built-in clients come from `keepsake/clients.py` (ADR-0032). When Peter sends the IDs, setting them there is the only change, and then the release flow needs nothing more from him.
6. **No new endpoint, scope or binary.**
   - **Hosts:** the backend talks only to the token endpoints already on the allowlist (`login.microsoftonline.com`, `oauth2.googleapis.com`). `accounts.google.com` is opened by the browser, never fetched by Keepsake.
   - **Scopes:** unchanged (`Files.ReadWrite.AppFolder offline_access`; `drive.appdata`).
   - **The listener:** it is loopback only and short-lived, so principle 17 (LAN exposure) does not apply. T101 records it.

## Registration (replaces ADR-0032's steps)

Microsoft (Entra admin centre, personal account):

1. **App registrations, New registration.** Name: `Keepsake`. Account types: "Personal Microsoft accounts only". Leave the redirect URI empty, then choose Register.
2. **Authentication.** Choose Add a platform, then "Mobile and desktop applications". Tick nothing, enter `http://localhost` as the custom redirect URI, then choose Configure.
3. **Authentication, Advanced settings.** Set "Allow public client flows" to Yes, then choose Save. The device code fallback needs this.
4. **API permissions.** Add Microsoft Graph delegated permissions `Files.ReadWrite.AppFolder` and `offline_access`.
5. **Overview.** Copy the "Application (client) ID" and send it.

Google (Google Cloud console):

1. **New project.** Name: `Keepsake`.
2. **APIs and services, Library.** Enable "Google Drive API".
3. **OAuth consent screen (Google Auth Platform).**
   - **Branding:** app name `Keepsake`, your support email.
   - **Audience:** External.
   - **Data access:** add the scope `https://www.googleapis.com/auth/drive.appdata`.
   - **Publish:** choose Publish app (Production).
4. **Clients, Create client: the browser sign-in.**
   - **Type:** "Desktop app", named `Keepsake desktop`. It needs no redirect URI, because Google allows loopback on any port for this type.
   - **Send:** its client ID and client secret.
5. **Clients, Create client again: the phone sign-in.**
   - **Type:** "TVs and Limited Input devices", named `Keepsake phone`. Google's device flow accepts only this type, and the browser flow accepts only "Desktop app", so one client cannot do both.
   - **Send:** its client ID and client secret too.

## After the IDs arrive (nothing more is needed from Peter)

1. **Fill in the IDs.** Put the OneDrive ID and the two Google pairs in `keepsake/clients.py`.
2. **Tests and scanner.**
   - Remove `test_shipped_constants_are_empty_until_the_owner_supplies_them`.
   - Add a scanner exception for the two `GOCSPX-` values in `clients.py` only (ADR-0032).
3. **Release.** Release with `python scripts/release.py`, signed as usual (ADR-0036).
4. **Device checks.** The next device run checks both sign-ins on a handheld and on a PC.

## The Gaming Mode probe

Diagnostics has a "Sign-in browser test" with three steps, run in Steam's browser on the Legion Go 2:

1. **Loopback.** Keepsake listens on `localhost` and opens it in Steam's browser. This confirms the redirect can reach Keepsake, and records whether it arrived over IPv4 or IPv6 and the browser's user agent.
2. **Microsoft.** Opens `https://login.live.com/`. Peter signs in and reports whether it worked or looped.
3. **Google.** Opens `https://accounts.google.com/`. Peter signs in and reports whether Google allowed it or showed "This browser or app may not be secure".

Each outcome is recorded with `record_probe_event`, so the diagnostics export carries it. A later change sets the Gaming Mode defaults from the results.

## Consequences

- **The default sign-in:** on a PC and in Desktop Mode, it is one button, a browser tab and Accept. In Gaming Mode, it is one button and Steam's browser where the provider allows it, otherwise the phone.
- **Waiting on others:**
  - the client IDs from Peter;
  - the probe run on the Legion Go 2, which decides the Gaming Mode defaults.
- **Two Google clients.** The built-in Google configuration holds two clients: the device code flow uses the TV client, and the browser flow uses the Desktop client. A user's own Google client is used for both. The phone sign-in needs it to be a TV client and the browser sign-in a Desktop client, and the Advanced hint says so.
- **The focus fix is unverified.** Restoring focus calls `focus()` on the Sign in button's DOM element. Whether Steam's gamepad focus follows it is part of the probe run.
