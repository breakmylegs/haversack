"""Rebuild the vendored pure-Python libraries in py_modules/keepsake/_vendor (ADR-0034).

    python scripts/vendor.py

Each library is a pinned wheel from PyPI, checked against its SHA-256 before it
is opened. Only the listed top-level packages are copied, the listed files are
left out, and the listed patches are applied (each must match exactly once).
The licence files go to ``_vendor/LICENSES``. ``_vendor/MANIFEST.json`` records
the SHA-256 of every file written, and ``tests/test_vendored.py`` fails if the
tree drifts from it. Run on the laptop only; the plugin never downloads code.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "py_modules", "keepsake", "_vendor")

TQDM_STUB = (
    "def tqdm(*args, **kwargs):  # Keepsake patch (ADR-0034): progress bars are never requested\n"
    '    raise RuntimeError("tqdm is not vendored with Keepsake")\n'
)

LIBRARIES = [
    {
        "name": "pysmb",
        "version": "1.2.15",
        "licence": "zlib/libpng",
        "url": "https://files.pythonhosted.org/packages/12/4a/5683a2244e7d8235612217936b33cd1ccded87371606afe4436b09cdc0b3/pysmb-1.2.15-py3-none-any.whl",
        "sha256": "f8459400dfcc9f1ec691936fc57d794803c4240516c27cb196024333f4947d7a",
        "packages": ["smb", "nmb"],
        "licence_file": "pysmb-1.2.15.dist-info/licenses/LICENSE",
        # Twisted front ends and the urllib handler: not used, and Twisted is not available.
        "drop": ["smb/SMBProtocol.py", "nmb/NetBIOSProtocol.py", "smb/SMBHandler.py"],
        # tqdm (MPL-2.0) is imported at module level but only used for show_progress=True.
        "patches": [
            ("smb/base.py", "from tqdm import tqdm\n", TQDM_STUB),
            ("smb/SMBConnection.py", "from tqdm import tqdm\n", TQDM_STUB),
        ],
    },
    {
        "name": "pyasn1",
        "version": "0.6.5",
        "licence": "BSD-2-Clause",
        "url": "https://files.pythonhosted.org/packages/19/1f/3eefd5c84c35cae44549ce1c7f7e58f7945b34f5a6bce07a135438522073/pyasn1-0.6.5-py3-none-any.whl",
        "sha256": "4017b0fce125096b8573b39c989fdb1a4b19cf761e683398184550fea0e66587",
        "packages": ["pyasn1"],
        "licence_file": "pyasn1-0.6.5.dist-info/licenses/LICENSE.rst",
        "drop": [],
        "patches": [],
    },
]


def fetch(url: str, sha256: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        sys.exit(f"hash mismatch for {url}: {digest}")
    return data


def build() -> dict[str, object]:
    if os.path.isdir(VENDOR):
        shutil.rmtree(VENDOR)
    os.makedirs(os.path.join(VENDOR, "LICENSES"))
    files: dict[str, str] = {}
    for lib in LIBRARIES:
        wheel = zipfile.ZipFile(io.BytesIO(fetch(str(lib["url"]), str(lib["sha256"]))))
        written: dict[str, bytes] = {}
        for name in wheel.namelist():
            top = name.split("/", 1)[0]
            if top in lib["packages"] and name.endswith(".py") and name not in lib["drop"]:
                written[name] = wheel.read(name)
        for path, old, new in lib["patches"]:  # type: ignore[attr-defined]
            text = written[path].decode("utf-8")
            if text.count(old) != 1:
                sys.exit(f"patch for {path} no longer matches")
            written[path] = text.replace(old, new).encode("utf-8")
        licence = f"LICENSES/{lib['name']}-{os.path.basename(str(lib['licence_file']))}"
        written[licence] = wheel.read(str(lib["licence_file"]))
        for rel, data in written.items():
            target = os.path.join(VENDOR, *rel.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(data)
            files[rel] = hashlib.sha256(data).hexdigest()
    with open(os.path.join(VENDOR, "__init__.py"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write('"""Vendored pure-Python libraries, rebuilt by scripts/vendor.py (ADR-0034). Do not edit."""\n')
    manifest = {
        "libraries": [
            {k: lib[k] for k in ("name", "version", "licence", "url", "sha256", "drop")}
            | {"patched": [p[0] for p in lib["patches"]]}  # type: ignore[attr-defined]
            for lib in LIBRARIES
        ],
        "files": dict(sorted(files.items())),
    }
    with open(os.path.join(VENDOR, "MANIFEST.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest


if __name__ == "__main__":
    print(f"{len(build()['files'])} files vendored")  # type: ignore[arg-type]
