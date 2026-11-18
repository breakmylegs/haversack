"""Replication's hard rules (ADR-0045): never through the cloud, never compressed.

The import checks read every module under ``keepsake/replication`` as source, so they hold
for code that later slices add. The checker itself is proven against synthetic code.
"""

import ast
import pathlib
import socket
import ssl
import threading

import pytest

from keepsake.replication import policy

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "py_modules" / "keepsake" / "replication"

# Cloud stores, the sync engine and cloud sign-in: Replication bytes and manifests never reach them.
CLOUD = ("keepsake.store", "keepsake.sync", "keepsake.auth", "keepsake.loopback_auth", "keepsake.app")
COMPRESSION = ("zlib", "gzip", "bz2", "lzma", "zstd", "compression", "zipfile", "tarfile", "shutil.make_archive")


def imported(source: str, package: str = "keepsake.replication") -> set[str]:
    """Every module a source file imports, with relative imports made absolute."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                base = f"{parent}.{base}" if base else parent
            names.add(base)
            names.update(f"{base}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and getattr(node.func, "id", "") == "__import__":
            names.add("__import__")  # dynamic imports would hide the rules
        elif isinstance(node, ast.Attribute) and node.attr == "import_module":
            names.add("importlib.import_module")
    return names


def violations(source: str, package: str = "keepsake.replication") -> list[str]:
    found = []
    for name in sorted(imported(source, package)):
        if any(name == c or name.startswith(c + ".") for c in CLOUD):
            found.append(f"cloud: {name}")
        if any(name == c or name.startswith(c + ".") for c in COMPRESSION):
            found.append(f"compression: {name}")
        if name in ("__import__", "importlib.import_module", "importlib"):
            found.append(f"dynamic import: {name}")
    return found


def test_no_replication_module_reaches_the_cloud_or_compresses():
    files = sorted(PACKAGE.rglob("*.py"))
    assert files, "the replication package exists"
    for path in files:
        package = "keepsake.replication" + "".join(f".{p}" for p in path.relative_to(PACKAGE).parent.parts)
        assert violations(path.read_text(encoding="utf-8"), package) == [], path.name


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from keepsake.store.graph import GraphStore", "cloud: keepsake.store.graph"),
        ("from ..store import Store", "cloud: keepsake.store"),
        ("from .. import sync", "cloud: keepsake.sync"),
        ("import keepsake.auth", "cloud: keepsake.auth"),
        ("from ..app import KeepsakeApp", "cloud: keepsake.app"),
        ("import zlib", "compression: zlib"),
        ("from gzip import compress", "compression: gzip"),
        ("import lzma, json", "compression: lzma"),
        ("import zipfile", "compression: zipfile"),
        ("x = __import__('zlib')", "dynamic import: __import__"),
        ("import importlib\nimportlib.import_module('zlib')", "dynamic import: importlib"),
    ],
)
def test_the_checker_catches_every_way_in(source, expected):
    assert expected in violations(source)


def test_the_checker_allows_what_replication_needs():
    allowed = "import ssl, hashlib, os, socket, asyncio\nfrom . import policy\nfrom ..fsutil import atomic_write_json"
    assert violations(allowed) == []


def test_tls_compression_is_off_and_checked():
    for purpose in (ssl.PROTOCOL_TLS_CLIENT, ssl.PROTOCOL_TLS_SERVER):
        context = ssl.SSLContext(purpose)
        context.options &= ~ssl.OP_NO_COMPRESSION  # as if a default changed
        assert policy.require_no_compression(context).options & ssl.OP_NO_COMPRESSION

    class Compressed:
        def compression(self):
            return "zlib"

    class Plain:
        def compression(self):
            return None

    policy.check_uncompressed(Plain())
    with pytest.raises(policy.PolicyError, match="compression"):
        policy.check_uncompressed(Compressed())


@pytest.mark.skipif(not getattr(ssl, "HAS_PSK", False), reason="this OpenSSL has no TLS-PSK")
def test_a_real_tls_connection_reports_no_compression():
    # TLS-PSK (one of slice 16's candidate transports) needs no certificate, so no key file is kept here.
    key = bytes(range(32))  # synthetic
    server_ctx = policy.require_no_compression(ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER))
    client_ctx = policy.require_no_compression(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    for context in (server_ctx, client_ctx):
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers("PSK")
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE
    server_ctx.set_psk_server_callback(lambda identity: key)
    client_ctx.set_psk_client_callback(lambda hint: ("peer", key))
    a, b = socket.socketpair()
    result = {}

    def serve():
        with server_ctx.wrap_socket(a, server_side=True) as conn:
            result["server"] = conn.compression()
            conn.recv(1)

    thread = threading.Thread(target=serve)
    thread.start()
    with client_ctx.wrap_socket(b) as conn:
        policy.check_uncompressed(conn)
        result["client"] = conn.compression()
        conn.sendall(b"x")
    thread.join(10)
    assert result == {"server": None, "client": None}


def test_space_margin_is_five_percent_or_two_gib():
    assert policy.space_needed(0) == 2 * policy.GIB
    assert policy.space_needed(10 * policy.GIB) == 12 * policy.GIB
    assert policy.space_needed(200 * policy.GIB) == 210 * policy.GIB


def test_slow_links_are_named_plainly():
    assert policy.link_verdict(80.0, 2.0) == {"slow": False, "megabytesPerSecond": 80.0, "rttMs": 2.0, "message": None}
    plain = policy.link_verdict(5.0, 2.0)["message"]
    assert "slow" in plain and "Tailscale" not in plain  # only a VPN or overlay link is blamed on a relay
    relayed = policy.link_verdict(40.0, 120.0, overlay=True)
    assert relayed["slow"] is True and "Tailscale" in relayed["message"]
