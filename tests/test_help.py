"""The in-app Help is the user guide, built by scripts/help.py and kept in step by the gate (R28, ADR-0090)."""

from __future__ import annotations

import importlib.util
import json
import os
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("help_script", os.path.join(ROOT, "scripts", "help.py"))
assert spec and spec.loader
help_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(help_script)


def data(text: str) -> list[dict[str, Any]]:
    return json.loads(text[text.index("= [") + 2 : text.rindex(";")])


def guide(tmp_path: Any, monkeypatch: Any) -> Any:
    user = tmp_path / "docs" / "user"
    user.mkdir(parents=True)
    (user / "README.md").write_text(
        "# Example guide\n\nIntro with a [link](https://example.com/page).\n\n"
        "- [First page](first.md): what it is.\n- [Trouble](../troubleshooting.md): messages.\n"
        "- [Changes](../../CHANGELOG.md).\n",
        encoding="utf-8",
    )
    (user / "first.md").write_text(
        "# First page\n\n![A screenshot](images/x.png)\n\nOpen **Settings** ![icon](i.png), then [Cloud](cloud.md).\n"
        "Second line of the same paragraph with `code`.\n\n"
        "1. Step one\n2. Step two\n   continued here\n   - nested point\n\n"
        "```mermaid\nsequenceDiagram\n    A->>B: hidden\n```\n\n"
        "| Service | Sees |\n|---|---|\n| OneDrive | `Apps/Keepsake` only |\n\n"
        "```\nhttps://example.com/x.zip\n```\n\n<details>Raw <b>html</b></details>\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "troubleshooting.md").write_text("# Troubleshooting\n\nRun checks.\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "desktop" / "src").mkdir(parents=True)
    monkeypatch.setattr(help_script, "ROOT", str(tmp_path))
    monkeypatch.setattr(help_script, "GUIDE", str(user))
    targets = (str(tmp_path / "src" / "help.ts"), str(tmp_path / "desktop" / "src" / "help.ts"))
    monkeypatch.setattr(help_script, "TARGETS", targets)
    return tmp_path


def test_topics_follow_the_index_and_blocks_are_plain(tmp_path: Any, monkeypatch: Any) -> None:
    guide(tmp_path, monkeypatch)
    topics = data(help_script.build())
    assert [(t["id"], t["title"]) for t in topics] == [
        ("readme", "About this guide"),
        ("first", "First page"),
        ("troubleshooting", "Trouble"),
    ]  # the changelog is not a guide page
    assert topics[0]["blocks"][1] == {"k": "p", "t": "Intro with a link (example.com/page)."}
    blocks = topics[1]["blocks"]
    assert blocks == [
        {"k": "h", "l": 1, "t": "First page"},
        {"k": "p", "t": "Open **Settings**, then Cloud. Second line of the same paragraph with code."},
        {"k": "li", "d": 0, "t": "1. Step one"},
        {"k": "li", "d": 0, "t": "2. Step two continued here"},
        {"k": "li", "d": 1, "t": "nested point"},
        {"k": "row", "t": "Service  |  Sees"},
        {"k": "row", "t": "OneDrive  |  Apps/Keepsake only"},
        {"k": "code", "t": "https://example.com/x.zip"},
        {"k": "p", "t": "Raw html"},
    ]  # no image, no diagram source, no markup


def test_both_copies_are_written_and_checked(tmp_path: Any, monkeypatch: Any, capsys: Any) -> None:
    root = guide(tmp_path, monkeypatch)
    assert help_script.main(["--check"]) == 1  # not built yet
    assert help_script.main([]) == 0
    gaming, desktop = (root / "src" / "help.ts").read_text(), (root / "desktop" / "src" / "help.ts").read_text()
    assert gaming == desktop and "export const HELP: HelpTopic[]" in gaming and "export type HelpBlock" in gaming
    assert help_script.main(["--check"]) == 0
    with open(root / "docs" / "user" / "first.md", "a", encoding="utf-8") as handle:
        handle.write("\nA new sentence.\n")
    capsys.readouterr()
    assert help_script.main(["--check"]) == 1  # the guide changed: the gate refuses until it is rebuilt
    assert "src/help.ts, desktop/src/help.ts not in step" in capsys.readouterr().out
    (root / "desktop" / "src" / "help.ts").write_text("edited by hand")
    help_script.main([])
    assert help_script.main(["--check"]) == 0


def test_the_repository_help_is_in_step_with_the_guide() -> None:
    names = [os.path.relpath(t, ROOT).replace(os.sep, "/") for t in help_script.TARGETS]
    assert names == ["src/help.ts", "desktop/src/help.ts"]  # Gaming Mode and the desktop app
    assert help_script.main(["--check"]) == 0


def test_the_gate_runs_the_help_check() -> None:
    with open(os.path.join(ROOT, "scripts", "check.py"), encoding="utf-8") as handle:
        assert '"scripts/help.py", "--check"' in handle.read()


def test_the_page_is_in_the_sidebar_and_the_desktop_app() -> None:
    with open(os.path.join(ROOT, "src", "routeData.ts"), encoding="utf-8") as handle:
        assert '{ id: "help", title: "Help", about: "The user guide.", parts: [part("help", "core")] }' in handle.read()
    with open(os.path.join(ROOT, "src", "pages", "KeepsakeRoute.tsx"), encoding="utf-8") as handle:
        assert "help: () => <HelpPage />" in handle.read()
    with open(os.path.join(ROOT, "desktop", "src", "main.ts"), encoding="utf-8") as handle:
        assert "render: (main) => helpPage(main)" in handle.read()
    with open(os.path.join(ROOT, "src", "pages", "HelpPage.tsx"), encoding="utf-8") as handle:
        page = handle.read()
    assert "autoFocus" not in page and "preferredFocus" not in page  # no page takes focus by itself (v0.41.1)
