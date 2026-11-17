# ADR-0032: Built-in OneDrive and Google Drive sign-in clients

- Status: accepted for OneDrive and Google Drive (Peter's request from his device run, 16 November 2026). The built-in IDs are empty until Peter supplies them; nothing is released until then.
- Date: 16 November 2026
- Deciders: Peter (owner)
- Supersedes: the "bring your own registration" default in ADR-0008 and slice 10, which stays available under Advanced
- Amended by: ADR-0044 (browser sign-in). Its registration steps replace the ones below; the Google project gains a second client, "Desktop app"

## Context

The setup wizard asked for a OneDrive client ID, and Google Drive for a client ID and secret. Peter wants sign-in to work like any other app: pick the provider, sign in on a phone with a normal account, and approve access to Keepsake's own app folder.

## Research (primary sources, read 16 November 2026)

**Microsoft**

- **Device code flow:** the client sends only `client_id` to `/devicecode` and `/token`, with no secret. The tenant segment is `/common`, `/consumers` or `/organizations`. Personal accounts sign in again on the phone and are shown the consent screen. Source: [OAuth 2.0 device authorization grant](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code).
- **App folder:** `Files.ReadWrite.AppFolder` gives read and write access to `Apps/<app name>` only. The folder takes the application name set when the folder is first created. Source: [What is an App Folder](https://learn.microsoft.com/en-us/onedrive/developer/rest-api/concepts/special-folders-appfolder).
- **Publisher verification:** since November 2020, if risk-based step-up consent is enabled, users can't consent to newly registered multi-tenant apps that aren't publisher verified. This applies to users in *other organisations' tenants*.
  - Verification needs a verified Microsoft AI Cloud Partner Program (Partner One) account and an app registered with a Microsoft Entra work or school account, with a publisher domain that isn't `*.onmicrosoft.com`.
  - "Apps that are registered by using a Microsoft account can't be publisher verified."
  - Source: [Publisher verification overview](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview).

**Google**

- **Device flow scopes:** the TVs and Limited Input device flow is supported only for a short list of scopes, including `drive.appdata` and `drive.file`. "Since the applications that use this flow are distributed to individual devices, it is assumed that the apps cannot keep secrets." Source: [OAuth 2.0 for TV and Limited-Input Device Applications](https://developers.google.com/identity/protocols/oauth2/limited-input-device).
- **Installed apps:** they are public clients that "cannot keep secrets confidential". Source: [OAuth 2.0 for iOS and Desktop Apps](https://developers.google.com/identity/protocols/oauth2/native-app).
- **Scope classification:** `drive.appdata` ("View and manage the app's own configuration data in your Google Drive") and `drive.file` are **non-sensitive**. Source: [Choose Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).
- **Testing mode:** limited to 100 test users, and "authorizations by a test user will expire seven days from the time of consent".
- **Production mode:** an unverified app shows the "Unverified apps" warning, and is capped at 100 new users over the project's lifetime, *only* when it requests sensitive or restricted scopes. The cap "does not apply if you are requesting only approved sensitive or restricted scopes."
- Source for both: [Manage App Audience](https://support.google.com/cloud/answer/15549945).
- **Verification:** all apps verify their brand (homepage and privacy policy on a verified domain) to show their name and logo. Sensitive and restricted scopes need more on top. Source: [OAuth app verification](https://support.google.com/cloud/answer/13464321).

## Decision

1. **OneDrive: one built-in public client, personal Microsoft accounts only.**
   - **Built-in default:** `keepsake/clients.py` holds `ONEDRIVE_CLIENT_ID`, empty until Peter supplies the registration's Application (client) ID. A public client ID is not a secret (ADR-0008, `docs/setup-entra.md`).
   - **When the ID is set:** the wizard and Settings show only "Sign in", and "Use my own client ID" moves under Advanced.
   - **Older settings:** settings that already hold a client ID keep using it. Every saved sign-in also records the client ID it was made with, and refreshes use that.
   - **Account types:** the authority stays `/consumers` (personal accounts). This fits OneDrive personal, where Keepsake's app folder lives, and avoids publisher verification entirely. That process needs a Partner Program account and a work-tenant registration with a custom domain, and still wouldn't help users whose organisation blocks consent. Supporting work or school accounts is a later decision for Peter (see "Registration" below).
2. **Google Drive: one built-in client, recommended, on these terms.**
   - **Client type:** "TVs and Limited Input devices", with only the non-sensitive scope `drive.appdata`.
   - **Publishing:** Production, not Testing. Testing would cap users at 100 and expire every sign-in after 7 days. In Production, non-sensitive scopes have no user cap and no unverified-app warning.
   - **Embedding the secret is expected:** Google's own device-flow and installed-app pages say these clients cannot keep secrets.
   - **Brand verification is optional:** a homepage and privacy policy on a domain Peter controls, so the consent screen shows the app's name and logo.
   - **Built-in default:** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `keepsake/clients.py`, empty until supplied. "Use my own Google client" moves under Advanced.
3. **The wizard** lists OneDrive first. The sign-in screen states exactly what is granted:
   - OneDrive: "Keepsake can read and write only the Apps/Keepsake folder in your OneDrive."
   - Google: "Keepsake's own hidden app folder in your Google Drive, never your files."
4. **Nothing else changes:** scopes, endpoints, the token store and the allowlist all stay as they are.

## Registration settings Peter needs

**OneDrive, Microsoft Entra admin center, App registrations, New registration**

- **Name:** `Keepsake`. This becomes the app folder name, `Apps/Keepsake`.
- **Supported account types:** *Personal Microsoft accounts only*.
- **Redirect URI:** none. Authentication, Advanced settings, **Allow public client flows: Yes**. The device code flow needs this.
- **API permissions:** Microsoft Graph, Delegated: **Files.ReadWrite.AppFolder** and **offline_access**. No admin consent is needed, because personal accounts consent themselves.
- **Certificates & secrets:** none. Keepsake never uses a secret.
- **Branding (optional):** a publisher domain, and a homepage and privacy statement URL. The consent screen shows the app name either way.
- Send me the **Application (client) ID**.
- **Work or school accounts later** need "Accounts in any organizational directory and personal Microsoft accounts" plus the authority changed to `/common`. In organisations with risk-based step-up consent, consent then also needs publisher verification (above).

**Google Drive, Google Cloud console**

- **Project:** create or choose a project. **APIs & Services, Library:** enable the **Google Drive API**.
- **OAuth consent screen (Google Auth Platform, Branding):** app name `Keepsake` and a support email. Data access: add the scope `.../auth/drive.appdata` only. Audience: External, and **Publish app** (Production).
- **Clients, Create client:** application type **TVs and Limited Input devices**. Send me the **client ID** and **client secret**. The secret isn't confidential for this client type; it ships in the app, as Google's own pages expect.
- **Brand verification (optional):** a homepage and privacy policy on a domain you control.

## Consequences

- Until the IDs are filled in, behaviour is unchanged: the bring-your-own fields show as before.
- `scripts/secret_scan.py` flags Google client secrets (`GOCSPX-`). The change that fills in `GOOGLE_CLIENT_SECRET` adds an exception for that one value in `clients.py` only, which Peter reviews in that pull request. The OneDrive ID is a GUID and is not flagged.
- `tests/test_builtin_clients.py` asserts the constants are empty, so they cannot be filled in by accident. The change that fills them removes that test.
- Turning the Advanced option off clears the user's own ID, so the next sign-in uses the built-in client. An existing sign-in keeps refreshing with the client it was made with (the Google refresh sends that client's own secret).
- Anyone can use Keepsake's built-in IDs in their own software. That's normal for public clients. Each user still consents, and the scopes are limited to Keepsake's own folders.
