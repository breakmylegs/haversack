"""Looks (R29 stage 1, ADR-0091): boot and suspend animations, and the theme plugins read only."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import pytest

from keepsake.looks import animations as anim
from keepsake.looks import themes

WEBM = anim.EBML + b"synthetic video"


def write(path: Any, data: bytes | str) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


def setup(tmp_path: Any) -> tuple[anim.Animations, Any]:
    steam = tmp_path / "steam"
    (steam / "config").mkdir(parents=True)
    write(tmp_path / "Videos" / "Aurora.webm", WEBM + b" aurora")
    write(tmp_path / "Videos" / "not-a-video.webm", b"plain text")
    write(tmp_path / "Videos" / "notes.txt", "x")
    write(tmp_path / "ac" / "Retro set" / "deck_startup.webm", WEBM + b" retro")
    write(tmp_path / "ac" / "Retro set" / "deeper" / "too-deep.webm", WEBM)
    a = anim.Animations(
        str(steam),
        str(tmp_path / "data"),
        [("Videos", str(tmp_path / "Videos")), ("Animation Changer", str(tmp_path / "ac"))],
        clock=lambda: 1_800_000_000,
    )
    return a, steam / "config" / "uioverrides" / "movies"


def test_choices_are_real_webm_files_one_level_deep(tmp_path: Any) -> None:
    a, _ = setup(tmp_path)
    assert [(c["id"], c["name"], c["from"]) for c in a.choices()] == [
        ("0:Aurora.webm", "Aurora", "Videos"),
        ("1:Retro set/deck_startup.webm", "Retro set/deck_startup", "Animation Changer"),
    ]


def test_set_and_reset_with_nothing_there_before(tmp_path: Any) -> None:
    a, movies = setup(tmp_path)
    assert a.status()["videos"]["boot"]["who"] == "steam"
    a.apply("boot", "0:Aurora.webm")
    assert (movies / "deck_startup.webm").read_bytes() == WEBM + b" aurora"
    assert not list(movies.glob("*.haversack-tmp"))
    found = a.status()["videos"]["boot"]
    assert found == {"who": "haversack", "name": "Aurora", "keptOriginal": False}
    a.reset("boot")
    assert not (movies / "deck_startup.webm").exists()
    assert a.status()["videos"]["boot"]["who"] == "steam"


def test_a_video_that_was_there_first_is_kept_and_brought_back(tmp_path: Any) -> None:
    a, movies = setup(tmp_path)
    write(movies / "steam_os_suspend.webm", WEBM + b" the user's own")
    assert a.status()["videos"]["suspend"]["who"] == "other"
    a.apply("suspend", "0:Aurora.webm")
    a.apply("suspend", "1:Retro set/deck_startup.webm")  # a second change keeps the first original, not ours
    assert a.status()["videos"]["suspend"]["keptOriginal"] is True
    a.reset("suspend")
    assert (movies / "steam_os_suspend.webm").read_bytes() == WEBM + b" the user's own"
    assert a.status()["videos"]["suspend"] == {"who": "other", "name": None, "keptOriginal": False}


def test_a_video_changed_by_another_tool_is_never_removed(tmp_path: Any) -> None:
    a, movies = setup(tmp_path)
    a.apply("throbber", "0:Aurora.webm")
    write(movies / "steam_os_suspend_from_throbber.webm", WEBM + b" another tool")
    assert a.status()["videos"]["throbber"]["who"] == "other"
    with pytest.raises(anim.AnimationError, match="changed outside"):
        a.reset("throbber")
    assert (movies / "steam_os_suspend_from_throbber.webm").read_bytes() == WEBM + b" another tool"


def test_only_choices_inside_the_source_folders_and_only_webm(tmp_path: Any) -> None:
    a, movies = setup(tmp_path)
    write(tmp_path / "secret.webm", WEBM)
    for bad in ("0:../secret.webm", "5:Aurora.webm", "x:Aurora.webm", "0:", "0:not-a-video.webm", "0:notes.txt"):
        with pytest.raises(anim.AnimationError):
            a.apply("boot", bad)
    with pytest.raises(anim.AnimationError, match="unknown"):
        a.apply("intro", "0:Aurora.webm")
    assert not movies.exists()


def test_too_big_files_are_not_offered(tmp_path: Any, monkeypatch: Any) -> None:
    a, _ = setup(tmp_path)
    monkeypatch.setattr(anim, "MAX_BYTES", len(WEBM) + 5)
    assert [c["name"] for c in a.choices()] == []  # both real videos are larger than the limit now


def test_a_bad_copy_changes_nothing(tmp_path: Any, monkeypatch: Any) -> None:
    a, movies = setup(tmp_path)
    real = anim._digest
    monkeypatch.setattr(anim, "_digest", lambda p: "bad" if p.endswith(".haversack-tmp") else real(p))
    with pytest.raises(anim.AnimationError, match="did not match"):
        a.apply("boot", "0:Aurora.webm")
    assert not (movies / "deck_startup.webm").exists() and not list(movies.glob("*.haversack-tmp"))


def test_without_steam_nothing_is_written(tmp_path: Any) -> None:
    a = anim.Animations(str(tmp_path / "no-steam"), str(tmp_path / "data"), [("Videos", str(tmp_path))])
    write(tmp_path / "Aurora.webm", WEBM)
    with pytest.raises(anim.AnimationError, match="config folder"):
        a.apply("boot", "0:Aurora.webm")
    assert a.status()["steamFound"] is False


def test_theme_plugins_themes_and_sounds_are_read_only_and_bounded(tmp_path: Any) -> None:
    hb = tmp_path / "homebrew"
    write(hb / "plugins" / "SDH-CssLoader" / "plugin.json", json.dumps({"name": "CSS Loader"}))
    write(hb / "plugins" / "anim" / "plugin.json", json.dumps({"name": "Animation Changer"}))
    write(hb / "plugins" / "broken" / "plugin.json", "{not json")
    write(
        hb / "themes" / "Clean" / "theme.json",
        json.dumps({"name": "Clean Gaming", "author": "someone", "version": "v1.2", "flags": ["PRESET"]}),
    )
    write(hb / "themes" / "Huge" / "theme.json", json.dumps({"name": "x" * 500, "author": ["not", "text"]}))
    write(hb / "themes" / "NoManifest" / "style.css", "body {}")
    write(hb / "sounds" / "Chimes" / "pack.json", json.dumps({"name": "Chimes", "author": "a", "music": True}))
    before = {p: p.read_bytes() for p in hb.rglob("*") if p.is_file()}
    found = themes.summary(str(hb))
    assert found["plugins"] == {"css": True, "audio": False, "animations": True}
    assert found["themes"] == [
        {"name": "Clean Gaming", "author": "someone", "version": "v1.2", "preset": True},
        {"name": "x" * 80, "author": "", "version": "", "preset": False},
    ]
    assert found["sounds"] == [{"name": "Chimes", "author": "a", "music": True}]
    assert {p: p.read_bytes() for p in hb.rglob("*") if p.is_file()} == before  # nothing written
    assert themes.summary(str(tmp_path / "nowhere")) == {
        "plugins": {"css": False, "audio": False, "animations": False},
        "themes": [],
        "sounds": [],
    }


def test_the_app_keeps_looks_off_until_switched_on_and_defers_to_animation_changer(tmp_path: Any) -> None:
    from keepsake.app import KeepsakeApp
    from keepsake.paths import PluginPaths

    home = tmp_path / "home"
    (home / ".steam" / "steam" / "config").mkdir(parents=True)
    write(home / "Videos" / "Aurora.webm", WEBM)
    paths = PluginPaths(*(str(tmp_path / n) for n in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(paths, auto_refresh_manifest=False, home=str(home))

    async def run() -> Any:
        status = await app.looks_status()
        assert status["enabled"] is False and status["choices"][0]["name"] == "Aurora"
        with pytest.raises(ValueError, match="Looks is off"):
            await app.looks_set_animation("boot", "2:Aurora.webm")
        await app.set_module_enabled("looks", True)
        done = await app.looks_set_animation("boot", "2:Aurora.webm")
        assert done["videos"]["boot"]["who"] == "haversack"
        write(home / "homebrew" / "plugins" / "anim" / "plugin.json", json.dumps({"name": "Animation Changer"}))
        assert (await app.looks_status())["animations"]["blockedBy"] == "Animation Changer"
        with pytest.raises(ValueError, match="Animation Changer manages"):
            await app.looks_reset_animation("boot")
        return home / ".steam" / "steam" / "config" / "uioverrides" / "movies" / "deck_startup.webm"

    target = asyncio.run(run())
    assert os.path.realpath(str(target)) and target.read_bytes() == WEBM


def test_the_first_original_survives_another_tool_and_a_second_choice(tmp_path: Any) -> None:
    a, movies = setup(tmp_path)
    write(movies / "deck_startup.webm", WEBM + b" first original")
    a.apply("boot", "0:Aurora.webm")
    write(movies / "deck_startup.webm", WEBM + b" another tool")  # replaced behind Haversack's back
    a.apply("boot", "1:Retro set/deck_startup.webm")
    a.reset("boot")
    assert (movies / "deck_startup.webm").read_bytes() == WEBM + b" first original"


def test_oversized_theme_manifests_are_skipped(tmp_path: Any, monkeypatch: Any) -> None:
    hb = tmp_path / "homebrew"
    write(hb / "themes" / "Big" / "theme.json", json.dumps({"name": "Big", "padding": "x" * 100}))
    write(hb / "themes" / "Small" / "theme.json", json.dumps({"name": "Small"}))
    monkeypatch.setattr(themes, "MAX_JSON", 60)
    assert [t["name"] for t in themes.summary(str(hb))["themes"]] == ["Small"]


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need POSIX here")
@pytest.mark.posix
def test_linked_videos_are_never_offered_or_followed(tmp_path: Any) -> None:
    a, _ = setup(tmp_path)
    write(tmp_path / "elsewhere.webm", WEBM)
    os.symlink(tmp_path / "elsewhere.webm", tmp_path / "Videos" / "Linked.webm")
    assert "Linked" not in [c["name"] for c in a.choices()]
    with pytest.raises(anim.AnimationError):
        a.apply("boot", "0:Linked.webm")
