"""The release signing public key pinned in the plugin (build prompt section 12, ADR-0023, ADR-0036).

Every update must carry a valid ``SHA256SUMS.minisig`` made with this key, or
Keepsake refuses to install it. The matching secret key is the owner's, sealed
on the release laptop (``scripts/signing.py``); it is never in this repository.
Pinned on 17 November 2026: versions before the release that carries this key
had no key and install it with the checksum check alone (ADR-0036).
"""

PUBLIC_KEY = "RWT/csb+ryShXSB/E4KrsSCvCNo9HTwBhAVwaOozYjWMieOmxYzwpZy9"
