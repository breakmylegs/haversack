"""Plain, readable secret and personal-data scan (threat model T11).

Usage:
    python scripts/secret_scan.py            scan every tracked file
    python scripts/secret_scan.py --staged   scan staged content (pre-commit hook)

Checks for token-shaped strings, private keys and email addresses. It also
reads an optional, git-ignored ``.secret-scan-denylist`` file: one string per
line (game names, device names, account names) that must never be committed.
Matching is case-insensitive. Lines starting with # are comments.

The build prompt (docs/build-prompt.md) is exempt from the denylist because
the owner chose to keep it in the repository as written.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENYLIST_FILE = ".secret-scan-denylist"
DENYLIST_EXEMPT = {"docs/build-prompt.md"}
SKIP_FILES = {"pnpm-lock.yaml"}
SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".woff", ".woff2"}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("minisign secret key", re.compile(r"untrusted comment: minisign encrypted secret\s+key")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("JSON Web Token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("Google OAuth client secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}")),
    (
        "assigned secret",
        re.compile(
            r"(?i)\b(client_secret|refresh_token|access_token|secret_access_key|password)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"
        ),
    ),
    ("email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]

EMAIL_ALLOW = re.compile(
    r"(@users\.noreply\.github\.com|noreply@anthropic\.com|@example\.(com|org|net)|you@you\.tld)$", re.IGNORECASE
)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def files_to_scan(staged: bool) -> list[str]:
    if staged:
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    else:
        out = git("ls-files")
    return [line for line in out.splitlines() if line]


def read_content(path: str, staged: bool) -> str | None:
    try:
        if staged:
            data = subprocess.run(["git", "show", f":{path}"], cwd=ROOT, check=True, capture_output=True).stdout
        else:
            with open(os.path.join(ROOT, path), "rb") as handle:
                data = handle.read()
    except (OSError, subprocess.CalledProcessError):
        return None
    if b"\x00" in data[:8000]:
        return None
    return data.decode("utf-8", errors="replace")


def load_denylist() -> list[str]:
    path = os.path.join(ROOT, DENYLIST_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip() and not line.startswith("#")]
    except FileNotFoundError:
        return []


def scan_text(path: str, text: str, denylist: list[str]) -> list[str]:
    findings: list[str] = []
    lowered_deny = [d.lower() for d in denylist]
    for number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            for match in pattern.finditer(line):
                if label == "email address" and EMAIL_ALLOW.search(match.group(0)):
                    continue
                findings.append(f"{path}:{number}: {label}")
        if path not in DENYLIST_EXEMPT:
            lowered = line.lower()
            for entry in lowered_deny:
                if entry in lowered:
                    findings.append(f"{path}:{number}: denylisted string")
    return findings


def main(argv: list[str]) -> int:
    staged = "--staged" in argv
    denylist = load_denylist()
    findings: list[str] = []
    for path in files_to_scan(staged):
        if os.path.basename(path) in SKIP_FILES or os.path.splitext(path)[1].lower() in SKIP_EXTENSIONS:
            continue
        text = read_content(path, staged)
        if text is not None:
            findings.extend(scan_text(path, text, denylist))
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"secret scan: {len(findings)} finding(s). Commit blocked.", file=sys.stderr)
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
