"""AWS Signature Version 4 on stdlib ``hmac`` and ``hashlib`` (build prompt section 11).

Header-based signing for S3 and S3-compatible services. The payload hash is
signed, so the service rejects a body that does not match it: uploads are
integrity-checked by the service itself.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from collections.abc import Mapping

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
ALGORITHM = "AWS4-HMAC-SHA256"


def _hmac(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def _encode(text: str, keep_slash: bool) -> str:
    return urllib.parse.quote(text, safe="/~" if keep_slash else "~")


def canonical_query(query: str) -> str:
    pairs = urllib.parse.parse_qsl(query, keep_blank_values=True)
    return "&".join(f"{_encode(k, False)}={_encode(v, False)}" for k, v in sorted(pairs))


def sign(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload_sha256: str,
    access_key: str,
    secret_key: str,
    region: str,
    service: str = "s3",
    now: float | None = None,
) -> dict[str, str]:
    """Return ``headers`` plus ``x-amz-date``, ``x-amz-content-sha256`` and ``Authorization``.

    ``url`` must already be percent-encoded as it will be sent.
    """
    parts = urllib.parse.urlsplit(url)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(time.time() if now is None else now))
    day = stamp[:8]
    host = parts.netloc
    signed = {k.lower(): " ".join(str(v).split()) for k, v in headers.items()}
    signed.update({"host": host, "x-amz-date": stamp, "x-amz-content-sha256": payload_sha256})
    names = sorted(signed)
    canonical_headers = "".join(f"{n}:{signed[n]}\n" for n in names)
    signed_names = ";".join(names)
    canonical = "\n".join(
        [
            method,
            parts.path or "/",
            canonical_query(parts.query),
            canonical_headers,
            signed_names,
            payload_sha256,
        ]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join([ALGORITHM, stamp, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode("utf-8"), day), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    out = {k: v for k, v in headers.items() if k.lower() != "host"}
    out["x-amz-date"] = stamp
    out["x-amz-content-sha256"] = payload_sha256
    out["Authorization"] = (
        f"{ALGORITHM} Credential={access_key}/{scope}, SignedHeaders={signed_names}, Signature={signature}"
    )
    return out
