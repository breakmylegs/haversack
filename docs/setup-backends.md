# WebDAV and S3 backends

Both are set up from Settings, Cloud, with the on-screen keyboard. Only HTTPS addresses are accepted, and Keepsake contacts only the host you enter. Passwords and secret keys are stored on the device with owner-only permissions and are never shown again; leave a secret field empty to keep the saved one.

Keepsake never overwrites a cloud object, so the server must refuse to replace an existing file. "Test connection" proves this by writing a small probe file (`registry/probe/<device id>.json`) twice; if the second write is accepted, Keepsake refuses the backend.

## WebDAV (for example Nextcloud or ownCloud)

- **Folder address**: the HTTPS address of an empty folder for Keepsake, ending in `/`. Nextcloud: `https://<server>/remote.php/dav/files/<user>/Keepsake/` (create the folder first).
- **User name** and **password**: for Nextcloud use an app password (Settings, Security, Devices and sessions).
- Nextcloud and ownCloud honour create-only writes. Some simple WebDAV servers do not, and Keepsake will say so.

## S3 and S3-compatible services

- **Endpoint**: for AWS, `https://s3.<region>.amazonaws.com`. For others, the HTTPS endpoint the service documents.
- **Region**: for AWS the bucket's region, for example `eu-west-2`; many compatible services accept `us-east-1`.
- **Bucket** and **folder inside the bucket** (default `keepsake`).
- **Access key ID** and **secret access key**: create a key that can only read, write, list and delete in that bucket and prefix.
- **Path-style addresses**: on for most compatible services; off for AWS virtual-hosted addresses if you prefer.
- AWS S3 supports conditional writes (`If-None-Match`). Check that a compatible service does; Keepsake refuses it otherwise.
