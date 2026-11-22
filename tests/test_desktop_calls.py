"""The desktop app's calls (desktop/src/main.ts) all exist in the host's call list, and its Reconnect help
page is registered (R24, ADR-0082). A call the host does not expose fails only when clicked, so this
catches it before a release."""

from __future__ import annotations

import os
import re

from keepsake import host

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def source() -> str:
    with open(os.path.join(ROOT, "desktop", "src", "main.ts"), encoding="utf-8") as handle:
        return handle.read()


def test_every_desktop_call_is_exposed_by_the_host() -> None:
    names = set(re.findall(r"\bcall(?:<[^>]*>)?\(\s*\"([a-z0-9_]+)\"", source()))
    assert len(names) > 20  # the pattern still finds the calls
    missing = sorted(names - set(host.CALLABLES) - set(host.HOST_CALLABLES))
    assert missing == []


def test_reconnect_help_page_is_registered() -> None:
    text = source()
    assert re.search(r'\{ id: "reconnect", title: "Reconnect help", group: "Device", render: reconnectPage \}', text)
    for name in (
        "reconnect_status",
        "reconnect_set_help",
        "reconnect_assist",
        "reconnect_diagnose",
        "reconnect_cable_pair",
    ):
        assert f'"{name}"' in text
