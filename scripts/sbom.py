"""A software bill of materials for a release (ADR-0050): CycloneDX 1.5 JSON, deterministic.

    python scripts/sbom.py [--out out/keepsake-sbom.cdx.json]

Lists what a release actually ships:
- the frontend packages Rollup bundles into ``dist/index.js``: the runtime
  ``dependencies`` in ``package.json``, at the versions ``pnpm-lock.yaml`` resolved.
  ``@decky/ui``, React and ReactDOM are provided by Decky Loader and Steam at run time,
  so they are not in the bundle and not listed;
- the vendored pure-Python libraries in ``py_modules/keepsake/_vendor`` (ADR-0034), with
  their wheel hashes.

No timestamp and a serial number derived from the version, so the same tag always
gives the same file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROVIDED_AT_RUN_TIME = {"@decky/ui", "react", "react-dom"}
SBOM_NAME = "keepsake-sbom.cdx.json"
REPOSITORY = "https://github.com/breakmylegs/keepsake/"


def asset_name(plugin: str, version: str) -> str:
    """The release asset's name, listed in the signed SHA256SUMS."""
    return f"{plugin}-v{version}.sbom.cdx.json"


def locked_versions(lockfile: str) -> dict[str, str]:
    """``name -> version`` for the root importer's dependencies in a pnpm 9 lockfile."""
    versions: dict[str, str] = {}
    in_root = in_deps = False
    name = None
    for line in lockfile.splitlines():
        if line.startswith("importers:"):
            continue
        if line.startswith("  .:"):
            in_root = True
            continue
        if in_root and re.match(r"^  \S", line):
            break  # the next importer
        if not in_root:
            continue
        if re.match(r"^    \S", line):
            in_deps = line.strip() == "dependencies:"
            continue
        if not in_deps:
            continue
        found = re.match(r"^      '?([^':]+)'?:\s*$", line)
        if found:
            name = found.group(1)
            continue
        found = re.match(r"^        version: (\S+)", line)
        if found and name:
            versions[name] = found.group(1).split("(", 1)[0]
            name = None
    return versions


def npm_component(name: str, version: str, licence: str) -> dict[str, Any]:
    return {
        "type": "library",
        "bom-ref": f"pkg:npm/{name}@{version}",
        "name": name,
        "version": version,
        "purl": f"pkg:npm/{name.replace('@', '%40', 1) if name.startswith('@') else name}@{version}",
        "licenses": [{"license": {"id": licence}}] if licence else [],
        "properties": [{"name": "keepsake:shipped-in", "value": "dist/index.js"}],
    }


def python_component(library: dict[str, Any]) -> dict[str, Any]:
    name, version = str(library["name"]), str(library["version"])
    licence = str(library.get("licence", ""))
    spdx = {"zlib/libpng": "Zlib"}.get(licence, licence)
    return {
        "type": "library",
        "bom-ref": f"pkg:pypi/{name}@{version}",
        "name": name,
        "version": version,
        "purl": f"pkg:pypi/{name}@{version}",
        "licenses": [{"license": {"id": spdx}}] if spdx else [],
        "hashes": [{"alg": "SHA-256", "content": str(library["sha256"])}],
        "externalReferences": [{"type": "distribution", "url": str(library["url"])}],
        "properties": [{"name": "keepsake:shipped-in", "value": "py_modules/keepsake/_vendor"}],
    }


def build(root: str = ROOT) -> dict[str, Any]:
    with open(os.path.join(root, "package.json"), encoding="utf-8") as handle:
        package = json.load(handle)
    names = sorted(n for n in package.get("dependencies", {}) if n not in PROVIDED_AT_RUN_TIME)
    locked: dict[str, str] = {}
    if names:
        with open(os.path.join(root, "pnpm-lock.yaml"), encoding="utf-8") as handle:
            locked = locked_versions(handle.read())
    components = []
    for name in names:
        version = locked.get(name)
        if version is None:
            raise SystemExit(f"{name} is not in pnpm-lock.yaml; run pnpm install")
        licence = ""
        meta_path = os.path.join(root, "node_modules", *name.split("/"), "package.json")
        if os.path.isfile(meta_path):
            with open(meta_path, encoding="utf-8") as handle:
                licence = str(json.load(handle).get("license", ""))
        components.append(npm_component(name, version, licence))
    with open(os.path.join(root, "py_modules", "keepsake", "_vendor", "MANIFEST.json"), encoding="utf-8") as handle:
        vendored = json.load(handle)
    components += [python_component(lib) for lib in sorted(vendored["libraries"], key=lambda lib: lib["name"])]
    version = str(package["version"])
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, REPOSITORY + version)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": f"keepsake@{version}",
                "name": "Keepsake",
                "version": version,
                "licenses": [{"license": {"id": "BSD-3-Clause"}}],
            }
        },
        "components": components,
    }


def write(out: str, root: str = ROOT) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(build(root), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(ROOT, "out", SBOM_NAME))
    print(write(parser.parse_args(argv).out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
