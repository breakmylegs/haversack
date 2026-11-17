# Setting up the OneDrive app registration

**Most people do not need this page.** Once a release carries Keepsake's built-in client (ADR-0032), you pick OneDrive, press **Sign in** and approve on your phone. This page is for the owner registering that built-in client, and for anyone who wants their own registration under **Advanced: use my own client ID**.

Keepsake signs in to OneDrive with Microsoft's device code flow: the handheld shows a code, and you finish sign-in on your phone. For that, Keepsake needs a **public client app registration** in Microsoft Entra. It takes about five minutes, once, from any browser.

A public client ID is not a secret. It identifies the app; it cannot be used to read anyone's files without that person signing in.

## Steps

1. Go to https://entra.microsoft.com (or https://portal.azure.com) and sign in with any Microsoft account. A personal account works; you may be asked to create a free directory.
2. Open **App registrations**, then **New registration**.
   - **Name:** `Keepsake`. OneDrive names the app folder after this (`Apps/Keepsake`).
   - **Supported account types:** **Personal Microsoft accounts only**.
   - **Redirect URI:** leave empty.
   - Select **Register**.
3. On the app's **Overview** page, copy the **Application (client) ID**. It looks like `00001111-aaaa-2222-bbbb-3333cccc4444`.
4. Open **Authentication**. Under **Advanced settings**, set **Allow public client flows** to **Yes**, then **Save**.
5. Open **API permissions**, then **Add a permission**, **Microsoft Graph**, **Delegated permissions**, and add:
   - `Files.ReadWrite.AppFolder`
   - `offline_access`

   Remove any other permission that was added by default (such as `User.Read`). Keepsake needs nothing else, and asking for more is not allowed by its rules.
6. No client secret and no certificate are needed. Do not create one.

## In Keepsake

1. Open Keepsake, Settings, **Cloud: OneDrive**. If the release has a built-in client, turn on **Advanced: use my own client ID**.
2. Enter the client ID with the on-screen keyboard and press **Save client ID**.
3. Press **Sign in**. Scan the QR code with your phone (or open `microsoft.com/devicelogin`), enter the code shown, sign in, and accept the permissions. Check that the page is on `microsoft.com` and names **Keepsake**.
4. The handheld shows "Signed in to OneDrive". Repeat on the other device with the same client ID and the same Microsoft account.

## What Keepsake can access

Only its own folder, `Apps/Keepsake` in your OneDrive. It cannot see any other file. You can see, back up or delete that folder in OneDrive like any other.

## The built-in client ID

Because it is not a secret, the owner's client ID is committed as `ONEDRIVE_CLIENT_ID` in `py_modules/keepsake/clients.py`, so new installs do not need to type it. A client ID you saved yourself is used instead, and every saved sign-in keeps refreshing with the client it was made with. Turning the Advanced option off clears your own ID; the built-in one is used from the next sign-in.
