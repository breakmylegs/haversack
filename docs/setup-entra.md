# Setting up your own OneDrive app registration

**Most people do not need this page.** Keepsake has a built-in OneDrive client (ADR-0032, ADR-0055): pick OneDrive, press **Sign in**, and approve with your Microsoft account. This page is for anyone who wants their own registration, under **Advanced: use my own client ID**.

A client ID is not a secret. It identifies the app; it cannot read anyone's files unless that person signs in.

## What you need

Microsoft registers apps inside a directory (a "tenant"). A personal Microsoft account gets one by signing up for a free Azure account. That needs a phone number and a non-prepaid debit or credit card. Microsoft places a temporary hold of about $1 and charges nothing unless you upgrade; you never need to upgrade. The registration itself is free.

## Steps (about 15 minutes, once)

1. Sign up at https://azure.microsoft.com/free with the Microsoft account you want the registration under. This creates a "Default Directory".
2. Go to https://entra.microsoft.com and sign in with the same account.
3. Open **Entra ID**, then **App registrations**, then **New registration**.
   - **Name:** `Keepsake`. OneDrive names the app folder after this (`Apps/Keepsake`).
   - **Supported account types:** **Personal accounts only**.
   - **Redirect URI:** leave empty.
   - Select **Register**.
4. On the **Overview** page, copy the **Application (client) ID**. It looks like `00001111-aaaa-2222-bbbb-3333cccc4444`.
5. Open **Authentication**, then **Add Redirect URI**, and choose the **Mobile and desktop applications** tile. Under **Custom redirect URIs**, enter `http://localhost`, then select **Configure**. Microsoft ignores the port for `localhost`, so Keepsake can listen on any free one (ADR-0044).
6. On **Authentication**, set **Allow public client flows** to **Yes**, and **Save**. In newer layouts it is on the **Settings** tab. This is the phone sign-in.
7. Open **API permissions**:
   - remove **User.Read** (the **...** menu on its row, then **Remove permission**);
   - select **Add a permission**, then **Microsoft Graph**, then **Delegated permissions**, and add `Files.ReadWrite.AppFolder` and `offline_access`.

   Keepsake needs nothing else, and its rules do not allow asking for more.
8. Do not create a client secret or a certificate.

## In Keepsake

1. Open Keepsake, Settings, **Cloud: OneDrive**, and turn on **Advanced: use my own client ID**.
2. Enter the client ID and press **Save client ID**.
3. Press **Sign in**, and approve in the browser or on your phone. Check that the page is on `microsoft.com` and names **Keepsake**.
4. Repeat on your other devices with the same client ID and the same Microsoft account.

## What Keepsake can access

Only its own folder, `Apps/Keepsake` in your OneDrive. It cannot see any other file. You can see, back up or delete that folder in OneDrive like any other.

## How the built-in client is chosen

The built-in client ID is `ONEDRIVE_CLIENT_ID` in `py_modules/keepsake/clients.py`. A client ID you saved yourself is used instead. Every saved sign-in keeps refreshing with the client it was made with. Turning the Advanced option off clears your own ID, and the built-in one is used from the next sign-in.
