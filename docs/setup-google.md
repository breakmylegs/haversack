# Setting up your own Google Drive clients

**Most people do not need this page.** Keepsake has built-in Google clients (ADR-0032, ADR-0055): pick Google Drive, press **Sign in**, and approve with your Google account. This page is for anyone who wants their own, under **Advanced: use my own client ID**.

Keepsake asks only for the `drive.appdata` scope. It sees its own hidden app folder in your Drive and nothing else.

## Two clients, one per sign-in method

| Sign-in | Client type |
|---|---|
| In a browser on this device (ADR-0044) | **Desktop app** |
| On your phone, with a code (device flow) | **TVs and Limited Input devices** |

Your own client is used for both methods, so create the type for the method you use. Google says neither type can keep its secret confidential, so the secret is stored on the device as an ordinary setting.

## Steps (about 15 minutes, once)

1. Go to https://console.cloud.google.com and create a project, for example `Keepsake`.
2. Search for **Google Drive API** in the top bar, open it, and select **Enable**.
3. Open the menu, then **Google Auth Platform**, then **Branding**, and select **Get started**:
   1. **App name** `Keepsake`, a **User support email**, then **Next**.
   2. **Audience:** **External**, then **Next**.
   3. **Contact information:** an email address, then **Next**.
   4. Agree to the user data policy, then **Continue** and **Create**.
4. Open **Data Access**, then **Add or Remove Scopes**. Tick only `.../auth/drive.appdata` (or paste `https://www.googleapis.com/auth/drive.appdata` under "Manually add scopes"), then **Update** and **Save**.
5. Open **Audience**, and under **Publishing status** select **Publish app**. `drive.appdata` is a non-sensitive scope, so a published app has no 100-user cap, no 7-day sign-in expiry and no "unverified app" warning (A156).
6. Open **Clients**, then **Create client**. Choose the **Application type** from the table above, give it a name, and select **Create**. Copy the **Client ID** and **Client secret**.

## In Keepsake

1. Settings, Cloud, Google Drive: turn on **Advanced: use my own client ID**.
2. Enter the client ID and client secret, then save. The secret is stored with owner-only permissions and never shown again; leave the field empty to keep it.
3. Sign in, and check the page is on `google.com` and names your app.
4. **Test connection**, then **Use Google Drive for snapshots**.
