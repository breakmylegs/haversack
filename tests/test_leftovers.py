"""What earlier versions left on the device (the strip, ADR-0098): only Haversack's own desktop entries go."""

import asyncio
import os

import pytest

from keepsake import leftovers
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

OURS = "[Desktop Entry]\nName=Haversack\nExec=python3 host.py\nX-Keepsake-Version=0.60.0\n"
THEIRS = "[Desktop Entry]\nName=My own launcher\nExec=something\n"


def entry(home, *parts):
    path = home.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_our_entries_are_removed_and_nothing_else(tmp_path):
    tray = entry(tmp_path, ".config", "autostart", "keepsake-tray.desktop")
    menu = entry(tmp_path, ".local", "share", "applications", "keepsake.desktop")
    other = entry(tmp_path, ".config", "autostart", "other.desktop")
    tray.write_text(OURS)
    menu.write_text(OURS)
    other.write_text(OURS)  # the marker, but not one of Haversack's names
    removed = leftovers.remove_desktop_entries(str(tmp_path))
    assert sorted(removed) == sorted([str(tray), str(menu)])
    assert not tray.exists() and not menu.exists() and other.exists()


def test_a_file_the_user_made_is_kept(tmp_path):
    tray = entry(tmp_path, ".config", "autostart", "keepsake-tray.desktop")
    tray.write_text(THEIRS)
    assert leftovers.remove_desktop_entries(str(tmp_path)) == []
    assert tray.read_text() == THEIRS


def test_nothing_there_is_fine(tmp_path):
    assert leftovers.remove_desktop_entries(str(tmp_path)) == []


@pytest.mark.posix
@pytest.mark.skipif(not hasattr(os, "symlink") or os.name == "nt", reason="symlinks need POSIX here")
def test_a_link_is_never_followed(tmp_path):
    target = tmp_path / "elsewhere.desktop"
    target.write_text(OURS)
    link = entry(tmp_path, ".config", "autostart", "keepsake-tray.desktop")
    os.symlink(target, link)
    assert leftovers.remove_desktop_entries(str(tmp_path)) == []
    assert target.exists() and os.path.islink(link)


def test_start_tidies_them(tmp_path):
    home = tmp_path / "home"
    tray = entry(home, ".config", "autostart", "keepsake-tray.desktop")
    tray.write_text(OURS)
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, proc_root=str(tmp_path / "proc"), home=str(home), auto_refresh_manifest=False)

    async def go():
        await app.start()
        await app.stop()

    asyncio.run(go())
    assert not tray.exists()
