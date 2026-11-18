"""R4, games from other launchers and emulator saves (ADR-0051). Synthetic launchers, prefixes and saves."""

import json
import os

import pytest

from helpers import write_fake_proc
from keepsake import launchers, procs, resolve
from keepsake.store import LocalFolderStore
from test_app_ux import Device, run

UID = os.getuid() if hasattr(os, "getuid") else -1


def write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def wine_prefix(path, user="deck"):
    os.makedirs(os.path.join(path, "drive_c", "users", user, "AppData", "Local"), exist_ok=True)
    os.makedirs(os.path.join(path, "drive_c", "users", "Public"), exist_ok=True)
    return str(path)


# Heroic


def heroic_home(tmp_path, flatpak=False):
    home = tmp_path / "home"
    root = home / (".var/app/com.heroicgameslauncher.hgl/config/heroic" if flatpak else ".config/heroic")
    prefix = wine_prefix(home / "Games/Heroic/Prefixes/Example Quest")
    proton = home / "Games/Heroic/Prefixes/Proton Racer"
    os.makedirs(proton / "pfx" / "drive_c", exist_ok=True)
    write(
        root / "store_cache/gog_library.json",
        json.dumps(
            {
                "games": [
                    {"app_name": "1111", "title": "Example Quest"},
                    {"app_name": "2222", "title": "Linux Only"},
                    {"app_name": "3333", "title": "Other Runner"},
                ]
            }
        ),
    )
    write(
        root / "gog_store/installed.json",
        json.dumps(
            {
                "installed": [
                    {"appName": "1111", "platform": "windows", "install_path": str(home / "Games/Example Quest")},
                    {"appName": "2222", "platform": "linux", "install_path": "/elsewhere"},
                    {"appName": "9999", "platform": "windows", "install_path": "/no-title"},
                    {"appName": "3333", "platform": "windows", "install_path": str(home / "Games/Other Runner")},
                ]
            }
        ),
    )
    write(
        root / "GamesConfig/3333.json",
        json.dumps({"3333": {"winePrefix": prefix, "wineVersion": {"type": "crossover"}}}),
    )
    write(root / "GamesConfig/1111.json", json.dumps({"1111": {"winePrefix": prefix, "wineVersion": {"type": "wine"}}}))
    write(
        home / ".config/legendary/installed.json",
        json.dumps(
            {"abcd": {"title": "Proton Racer", "platform": "Windows", "install_path": str(home / "Games/Proton Racer")}}
        ),
    )
    write(
        root / "GamesConfig/abcd.json",
        json.dumps({"abcd": {"winePrefix": str(proton), "wineVersion": {"type": "proton"}}}),
    )
    return home, prefix, str(proton)


def test_heroic_gog_and_epic_games_with_their_wine_and_proton_prefixes(tmp_path):
    home, prefix, proton = heroic_home(tmp_path)
    games = {g["key"]: g for g in launchers.heroic_games(str(home))}
    assert set(games) == {"heroic:gog:1111", "heroic:gog:3333", "heroic:epic:abcd"}  # no Linux or untitled games
    other = games["heroic:gog:3333"]
    assert other["prefix"] is None and "wine_prefix" not in other  # a runner Keepsake does not know: no prefix
    gog, epic = games["heroic:gog:1111"], games["heroic:epic:abcd"]
    assert gog["name"] == "Example Quest" and gog["wine_prefix"] == prefix and gog["wine_user"] == "deck"
    assert gog["prefix"] is None and gog["base_dir"].endswith("Example Quest") and gog["kind"] == "heroic"
    assert "GOG" in gog["notes"][0]
    assert epic["prefix"] == proton and "wine_prefix" not in epic  # Proton: resolved like Steam's prefixes


def test_heroic_flatpak_is_read_too(tmp_path):
    home, _, _ = heroic_home(tmp_path, flatpak=True)
    assert "heroic:gog:1111" in {g["key"] for g in launchers.heroic_games(str(home))}


# Lutris and Bottles


def test_simple_yaml_reads_nested_scalars_and_skips_what_it_cannot_read():
    text = (
        "name: \"Example Quest\"\ngame:\n  prefix: /p\n  exe: '/p/drive_c/g.exe'\n  args:\n    - -x\n"
        "system:\n  env: |\n"
    )
    assert launchers.simple_yaml(text) == {
        "name": "Example Quest",
        "game": {"prefix": "/p", "exe": "/p/drive_c/g.exe", "args": {}},
        "system": {"env": {}},
    }


def test_lutris_wine_games_with_names_from_the_database_or_the_file(tmp_path):
    home = tmp_path / "home"
    prefix = wine_prefix(home / "Games/example-quest")
    write(
        home / ".config/lutris/games/example-quest-1.yml",
        f"game:\n  exe: {prefix}/drive_c/Games/EQ/eq.exe\n  prefix: {prefix}\nname: From File\n",
    )
    write(home / ".config/lutris/games/native-2.yml", "game:\n  exe: /usr/bin/native\nname: Native Game\n")
    games = launchers.lutris_games(str(home), names_from_db={"example-quest-1": "Example Quest"})
    assert [(g["key"], g["name"]) for g in games] == [("lutris:example-quest-1", "Example Quest")]
    assert games[0]["wine_prefix"] == prefix and games[0]["base_dir"].endswith("EQ")
    assert launchers.lutris_games(str(home), names_from_db={})[0]["name"] == "From File"


def test_bottles_programs_use_their_bottle_as_the_prefix(tmp_path):
    home = tmp_path / "home"
    bottle = wine_prefix(home / ".var/app/com.usebottles.bottles/data/bottles/bottles/Gaming")
    write(
        os.path.join(bottle, "bottle.yml"),
        "Name: Gaming\nExternal_Programs:\n  1a2b:\n    name: Example Quest\n    path: C:\\\\Games\\\\eq.exe\n"
        "  3c4d:\n    path: C:\\\\nameless.exe\n",
    )
    games = launchers.bottles_programs(str(home))
    assert [(g["key"], g["name"], g["wine_prefix"]) for g in games] == [
        ("bottles:Gaming:1a2b", "Example Quest", bottle)
    ]


# Emulators


def test_emulators_appear_only_when_their_save_folder_exists_and_share_one_key(tmp_path):
    home = tmp_path / "home"
    os.makedirs(home / ".var/app/org.libretro.RetroArch/config/retroarch/saves")
    found = launchers.emulator_entries(str(home))
    assert [g["key"] for g in found] == ["emulator:retroarch"]
    entry = found[0]
    assert launchers.emulator_game_key(entry) == "emulator-retroarch"
    assert entry["flatpak_id"] == "org.libretro.RetroArch" and entry["kind"] == "emulator"
    assert entry["emulator_paths"] == [
        {"root": "home", "rel": ".var/app/org.libretro.RetroArch/config/retroarch/saves"}
    ]
    assert entry["states_paths"][0]["rel"].endswith("/states")
    for profile in launchers.load_emulators():  # every profile is canonical: home-relative, no absolute paths
        for path in profile["saves"] + profile.get("states", []):
            assert path["root"] == "home" and not path["rel"].startswith("/")


def test_a_failing_launcher_never_hides_the_others(tmp_path, monkeypatch):
    home = tmp_path / "home"
    os.makedirs(home / ".var/app/org.libretro.RetroArch/config/retroarch/saves")

    def broken(_home):
        raise ValueError("unreadable")

    monkeypatch.setattr(launchers, "heroic_games", broken)
    assert [g["key"] for g in launchers.discover_all(str(home))] == ["emulator:retroarch"]


# Save roots and running checks


def test_a_wine_prefix_resolves_with_the_linux_user_and_fails_closed_without_one(tmp_path):
    prefix = wine_prefix(tmp_path / "prefix", user="player")
    game = {"key": "lutris:x", "kind": "lutris", "wine_prefix": prefix, "wine_user": launchers.wine_user(prefix)}
    roots = resolve.logical_roots(game, home=str(tmp_path))
    assert roots["winLocalAppData"] == os.path.join(prefix, "drive_c", "users", "player", "AppData", "Local")
    assert roots["winProgramData"] == os.path.join(prefix, "drive_c", "ProgramData")
    assert roots["home"] is None and resolve.platform_of(game) == "proton"
    os.makedirs(os.path.join(prefix, "drive_c", "users", "second"))
    assert launchers.wine_user(prefix) is None  # two users: unsure, so no user folders at all
    unsure = resolve.logical_roots({**game, "wine_user": None}, home=str(tmp_path))
    assert unsure["winLocalAppData"] is None and unsure["winPublic"].endswith(os.path.join("users", "Public"))


def test_launcher_games_and_emulators_count_as_running_by_prefix_flatpak_or_program(tmp_path):
    proc = str(tmp_path / "proc")
    prefix = wine_prefix(tmp_path / "prefix")
    wine_game = {"kind": "heroic", "wine_prefix": prefix}
    emulator = {"kind": "emulator", "flatpak_id": "org.libretro.RetroArch", "process_names": []}
    appimage = {"kind": "emulator", "flatpak_id": None, "process_names": ["rpcs3"]}
    for game in (wine_game, emulator, appimage):
        assert procs.launcher_running(game, proc, uid=UID) is False
    write_fake_proc(proc, 501, 1, "game.exe", uid=UID, env={"WINEPREFIX": prefix + "/"})
    write_fake_proc(proc, 502, 1, "retroarch", uid=UID, env={"FLATPAK_ID": "org.libretro.RetroArch"})
    write_fake_proc(proc, 503, 1, "AppRun", uid=UID, cmdline="/tmp/.mount_x/usr/bin/rpcs3 --no-gui")
    for game in (wine_game, emulator, appimage):
        assert procs.launcher_running(game, proc, uid=UID) is True
    write_fake_proc(str(tmp_path / "other"), 601, 1, "game.exe", uid=UID + 1, env={"WINEPREFIX": prefix})
    assert procs.launcher_running(wine_game, str(tmp_path / "other"), uid=UID) is False  # another user's process


# The app, end to end


def emulator_device(tmp_path, name, appid, shared):
    device = Device(tmp_path, name, appid, shared)
    home = tmp_path / name / "home"
    saves = home / ".var/app/org.libretro.RetroArch/config/retroarch/saves"
    saves.mkdir(parents=True)
    return device, saves


def test_emulator_saves_sync_between_devices_and_wait_while_the_emulator_runs(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    a, a_saves = emulator_device(tmp_path, "a", 4171510507, shared)
    b, b_saves = emulator_device(tmp_path, "b", 4171510999, shared)

    async def go():
        for device in (a, b):
            games = {g["key"]: g for g in (await device.app.discover_games(True))["games"]}
            assert games["emulator:retroarch"]["name"] == "Emulator saves: RetroArch"
            config = device.app.game_configs.get("emulator:retroarch")
            assert config["gameKey"] == "emulator-retroarch" and config["enabled"] is False
            await device.app.update_game_config("emulator:retroarch", {"enabled": True})
        states = {"root": "home", "rel": ".var/app/org.libretro.RetroArch/config/retroarch/states"}
        mine = device.app.game_configs.get("emulator:retroarch")["customPaths"] + [states]
        await a.app.update_game_config("emulator:retroarch", {"customPaths": mine})
        await a.app.discover_games(True)  # found again: the user's choice is kept, not reset
        assert states in a.app.game_configs.get("emulator:retroarch")["customPaths"]
        (a_saves / "Example Quest.srm").write_bytes(b"battery save v1")
        await a.app.idle_pass()  # pushed from a
        await b.app.idle_pass()  # b adopts: same key, first sync
        (a_saves / "Example Quest.srm").write_bytes(b"battery save v2")
        await a.app.idle_pass()
        uid = os.getuid() if hasattr(os, "getuid") else -1
        write_fake_proc(
            str(tmp_path / "b" / "proc"), 700, 1, "retroarch", uid=uid, env={"FLATPAK_ID": "org.libretro.RetroArch"}
        )
        await b.app.idle_pass()  # newer save exists, but RetroArch runs on b: nothing is replaced
        while_running = (b_saves / "Example Quest.srm").read_bytes()
        os.remove(tmp_path / "b" / "proc" / "700" / "stat")
        await b.app.idle_pass()
        await b.app.idle_pass()  # the first pass notes the newer save, the next brings it in
        return while_running

    while_running = run(go())
    assert while_running == b"battery save v1"
    assert (b_saves / "Example Quest.srm").read_bytes() == b"battery save v2"


def test_launchers_can_be_switched_off_and_never_appear_on_windows(tmp_path):
    shared = LocalFolderStore(str(tmp_path / "cloud"))
    device, _ = emulator_device(tmp_path, "a", 4171510507, shared)

    async def keys():
        return {g["key"] for g in (await device.app.discover_games(True))["games"]}

    assert "emulator:retroarch" in run(keys())
    run(device.app.set_setting("otherLaunchers", False))
    assert "emulator:retroarch" not in run(keys())
    run(device.app.set_setting("otherLaunchers", True))
    device.app.host = "windows"
    assert "emulator:retroarch" not in run(keys())


@pytest.fixture(autouse=True)
def _no_real_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "no-real-home"))
