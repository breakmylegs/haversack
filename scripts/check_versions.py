"""Fail if any version field disagrees with package.json (build prompt section 13).

* package.json is the only place a version is written.
* plugin.json must not carry a version.
* CHANGELOG.md must have a section for the version.
* On a tag build, the tag must be v<version>.
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-beta\.\d+)?$")


def main() -> int:
    errors: list[str] = []
    with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as handle:
        version = json.load(handle)["version"]
    if not SEMVER.match(version):
        errors.append(f"package.json version {version!r} is not X.Y.Z or X.Y.Z-beta.N")
    with open(os.path.join(ROOT, "plugin.json"), encoding="utf-8") as handle:
        if "version" in json.load(handle):
            errors.append("plugin.json must not contain a version; package.json is the source of truth")
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as handle:
        changelog = handle.read()
    if not re.search(rf"^## \[{re.escape(version)}\]", changelog, re.MULTILINE):
        errors.append(f"CHANGELOG.md has no '## [{version}]' section")
    ref_type = os.environ.get("GITHUB_REF_TYPE")
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    if ref_type == "tag" and ref_name != f"v{version}":
        errors.append(f"tag {ref_name!r} does not match package.json version v{version}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if not errors:
        print(f"version {version} is consistent")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
