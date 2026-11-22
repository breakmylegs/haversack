"""v0.39.1: the full page's sidebar logic (src/sidebar.ts), compiled with tsc and run with Node's test runner."""

import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPX = shutil.which("npx") or shutil.which("npx.cmd")


@pytest.mark.skipif(NPX is None or shutil.which("node") is None, reason="needs Node")
def test_sidebar(tmp_path):
    out = str(tmp_path / "out")
    sources = [os.path.join(ROOT, "src", n) for n in ("sidebar.ts", "routeData.ts")]
    compiled = subprocess.run(
        [
            NPX,
            "-y",
            "pnpm@9.15.9",
            "exec",
            "tsc",
            "--outDir",
            out,
            "--module",
            "commonjs",
            "--target",
            "es2020",
            "--strict",
            "--skipLibCheck",
            *sources,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        shell=sys.platform == "win32" and NPX.endswith(".cmd"),
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    run = subprocess.run(
        ["node", "--test", os.path.join(ROOT, "tests", "frontend", "sidebar.test.cjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "KEEPSAKE_FRONTEND_OUT": out},
    )
    assert run.returncode == 0, run.stdout + run.stderr
