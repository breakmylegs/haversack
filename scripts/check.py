"""Local quality gate, run before every pull request (ADR-0004).

Runs the static checks and the build: ESLint, tsc, Rollup, version
consistency, packaging, ruff, mypy, the secret scan, the user guide check and the
performance budget. It does not run the
test suite: run the tests for what you changed, named one by one, and the
posix-marked tests on a device with scripts/test_on_device.py.

    python scripts/check.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pnpm() -> list[str]:
    if shutil.which("pnpm"):
        return ["pnpm"]
    return ["npx", "-y", "pnpm@9.15.9"]


def venv_tool(name: str) -> list[str]:
    folder = "Scripts" if os.name == "nt" else "bin"
    candidate = os.path.join(ROOT, ".venv", folder, name + (".exe" if os.name == "nt" else ""))
    return [candidate] if os.path.exists(candidate) else [name]


STEPS: list[tuple[str, list[str]]] = [
    ("eslint", [*pnpm(), "run", "lint"]),
    ("tsc", [*pnpm(), "run", "typecheck"]),
    ("build", [*pnpm(), "run", "build"]),
    ("desktop", [*pnpm(), "run", "build:desktop"]),  # the PC desktop interface (ADR-0040)
    ("versions", [sys.executable, "scripts/check_versions.py"]),
    ("package", [sys.executable, "scripts/package.py"]),
    ("ruff", [*venv_tool("ruff"), "check", "."]),
    ("ruff format", [*venv_tool("ruff"), "format", "--check", "."]),
    ("mypy", venv_tool("mypy")),
    ("secret scan", [sys.executable, "scripts/secret_scan.py"]),
    ("docs", [sys.executable, "scripts/check_docs.py"]),  # the user guide's links, images and sample data (ADR-0046)
    ("help", [sys.executable, "scripts/help.py", "--check"]),  # the in-app Help is the user guide (ADR-0090)
    ("perf", [sys.executable, "scripts/perf_budget.py"]),  # hot paths at 500 games and 10,000 snapshots (ADR-0050)
]


def main() -> int:
    failed: list[str] = []
    for label, command in STEPS:
        print(f"== {label}", flush=True)
        # shell=True only on Windows, where pnpm and npx are .cmd shims.
        result = subprocess.run(command, cwd=ROOT, shell=os.name == "nt", check=False)
        if result.returncode != 0:
            failed.append(label)
    print("== all checks passed" if not failed else f"== failed: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
