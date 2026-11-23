"""Launch option presets (R29 stage 5, ADR-0097): Proton's own variables, everything else kept exactly,
the original kept first, and nothing while the strict launch gate manages the options. Synthetic (P12)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from keepsake import launchopts as lo
from test_app_ux import Device


def test_presets_go_in_front_of_command_and_everything_else_is_kept() -> None:
    assert lo.compose("", ["log"]) == "PROTON_LOG=1 %command%"
    assert lo.compose("-dx11 -windowed", ["log"]) == "PROTON_LOG=1 %command% -dx11 -windowed"
    assert lo.compose("gamemoderun DXVK_HUD=fps %command% -dx11", ["wined3d", "log"]) == (
        "PROTON_LOG=1 PROTON_USE_WINED3D=1 gamemoderun DXVK_HUD=fps %command% -dx11"
    )
    assert lo.compose('MY_PATH="a b" %command% --name "Two words"', ["nofsync"]) == (
        "PROTON_NO_FSYNC=1 'MY_PATH=a b' %command% --name 'Two words'"
    )


def test_switching_presets_off_removes_only_them() -> None:
    line = "PROTON_LOG=1 PROTON_NO_FSYNC=1 OTHER=1 %command% -x"
    assert lo.compose(line, ["nofsync"]) == "PROTON_NO_FSYNC=1 OTHER=1 %command% -x"
    assert lo.compose(line, []) == "OTHER=1 %command% -x"
    assert lo.compose("-dx11", []) == "-dx11"  # arguments only stay arguments only
    assert lo.compose("PROTON_LOG=1 %command%", []) == "%command%"


def test_which_presets_are_on() -> None:
    assert lo.active("PROTON_LOG=1 PROTON_USE_WINED3D=1 %command%") == ["log", "wined3d"]
    assert lo.active("PROTON_LOG=0 %command%") == []  # only =1 counts as on
    assert lo.active("%command% PROTON_LOG=1") == []  # after %command% it is an argument
    assert lo.active("") == []


def test_bad_lines_and_unknown_presets_are_refused() -> None:
    with pytest.raises(lo.LaunchError, match="unmatched quote"):
        lo.compose('MY="broken %command%', ["log"])
    with pytest.raises(lo.LaunchError, match="unknown"):
        lo.compose("", ["rm -rf"])
    with pytest.raises(lo.LaunchError, match="too long"):
        lo.compose("-x " * 400, ["log"])
    assert lo.status('A="broken', None)["problem"]


def test_the_first_original_is_kept(tmp_path: Any) -> None:
    store = lo.Originals(str(tmp_path))
    store.keep(4000001, "-dx11")
    store.keep(4000001, "PROTON_LOG=1 %command% -dx11")  # a later change never replaces the original
    assert store.get(4000001) == "-dx11"
    store.forget(4000001)
    assert store.get(4000001) is None


@pytest.fixture
def device(tmp_path: Any) -> Any:
    from keepsake.store import LocalFolderStore

    return Device(tmp_path, "a", 4171510507, LocalFolderStore(str(tmp_path / "cloud")))


def test_the_app_keeps_the_original_and_puts_it_back(device: Any) -> None:
    app = device.app

    async def run() -> Any:
        seen = await app.launch_presets(device.key, "-dx11")
        assert [p["on"] for p in seen["presets"]] == [False] * len(lo.PRESETS) and seen["original"] is None
        applied = await app.launch_apply(device.key, "-dx11", ["log"])
        assert applied == {"appid": 4171510507, "options": "PROTON_LOG=1 %command% -dx11"}
        again = await app.launch_apply(device.key, applied["options"], ["log", "nofsync"])
        assert again["options"] == "PROTON_LOG=1 PROTON_NO_FSYNC=1 %command% -dx11"
        seen = await app.launch_presets(device.key, again["options"])
        assert seen["original"] == "-dx11" and [p["id"] for p in seen["presets"] if p["on"]] == ["log", "nofsync"]
        back = await app.launch_restore(device.key)
        assert back == {"appid": 4171510507, "options": "-dx11"}
        with pytest.raises(ValueError, match="has not changed"):
            await app.launch_restore(device.key)

    asyncio.run(run())


def test_nothing_while_the_strict_launch_gate_manages_the_options(device: Any) -> None:
    app = device.app

    async def run() -> None:
        await app.update_game_config(device.key, {"launchGate": "strict"})
        assert (await app.launch_presets(device.key, ""))["strict"] is True
        with pytest.raises(ValueError, match="strict launch gate"):
            await app.launch_apply(device.key, "", ["log"])
        with pytest.raises(ValueError, match="strict launch gate"):
            await app.launch_restore(device.key)

    asyncio.run(run())
