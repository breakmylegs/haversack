# Set up Google Drive for Keepsake

Keepsake signs in to Google Drive with the device flow for TVs and limited-input devices, so you finish sign-in on your phone. Because the Keepsake repository is public, it ships no Google credentials: you create your own once. Keepsake asks only for the `drive.appdata` scope, so it can see its own hidden app folder in your Drive and nothing else.

## Create the credentials (once, on a computer or phone browser)

1. Open the Google Cloud console and create a project, for example "Keepsake".
2. APIs and services, Library: enable the **Google Drive API**.
3. APIs and services, OAuth consent screen: choose **External**, give the app a name (for example "Keepsake"), add your own email as a test user. Add the scope `.../auth/drive.appdata`. Leaving the app in testing mode works for your own account, but Google then expires the sign-in after 7 days and you sign in again from Settings. Publishing the app avoids that; check the consent screen page for whether Google asks for verification for this scope (unverified, A116).
4. APIs and services, Credentials, Create credentials, **OAuth client ID**, application type **TVs and Limited Input devices**.
5. Copy the client ID and the client secret.

## In Keepsake (Gaming Mode)

1. Settings, Cloud, Google Drive.
2. Enter the client ID and client secret with the on-screen keyboard, then Save settings.
3. Sign in: open the address shown (or scan the QR code) on your phone, check the page is on google.com and names your app, and enter the code.
4. Test connection, then "Use Google Drive for snapshots".

The secret is stored on the device with owner-only permissions and is never shown again; leave the field empty to keep it.
