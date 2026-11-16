"""The release signing public key pinned in the plugin (build prompt section 12, ADR-0023).

Empty until the owner creates a minisign key (``docs/releasing.md``) and pastes
the public key's base64 line here. While it is empty, updates are installed with
the SHA-256 check only and the Updates page says releases are not signed. Once
it is set, every update must carry a valid ``SHA256SUMS.minisig`` made with this
key, or Keepsake refuses to install it.
"""

PUBLIC_KEY = ""
