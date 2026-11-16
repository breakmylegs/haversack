"""Performance check with 50 games (build prompt slice 12).

Builds a synthetic Steam install with 50 non-Steam shortcuts, each with its own
prefix and a few save files, and times what a player triggers: scanning,
matching, previewing, the setup wizard's dry run, the Quick Access Menu
summary, health checks, a first push of every game and an idle pass. Budgets
are generous (laptop and handheld differ) and catch regressions of an order of
magnitude, not small slow-downs. Run with ``-s`` to see the timings.
"""

import asyncio
import time

from helpers import make_fake_steam, shortcut_entry
from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths

GAMES = 50
BUDGET_SECONDS = {
    "discover": 10,
    "match_games": 15,
    "preview_each": 30,
    "plan_sync": 60,
    "qam_summary": 10,
    "health_checks": 15,
    "first_push_all": 180,
    "idle_pass": 120,
}


def build(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    shortcuts, prefixes, manifest = [], [], ["---"]
    for n in range(GAMES):
        appid = 4000000000 + n
        shortcuts.append(shortcut_entry(appid - 2**32, f"Perf Game {n:02d}", f"/g{n}.exe"))
        prefixes.append((None, appid))
        manifest += [
            f"Perf Game {n:02d}:",
            "  files:",
            f'    "<winLocalAppData>/PerfGame{n:02d}":',
            "      tags:",
            "        - save",
        ]
    root = make_fake_steam(home, users={"7": shortcuts}, prefixes=prefixes, most_recent="7")
    for n in range(GAMES):
        saves = (
            root
            / "steamapps/compatdata"
            / str(4000000000 + n)
            / f"pfx/drive_c/users/steamuser/AppData/Local/PerfGame{n:02d}"
        )
        saves.mkdir(parents=True)
        for slot in range(5):
            (saves / f"slot{slot}.sav").write_bytes(bytes([n, slot]) * 2048)
    paths = PluginPaths(*(str(tmp_path / x) for x in ("settings", "runtime", "logs", "plugin")))
    app = KeepsakeApp(
        paths, proc_root=str(tmp_path / "proc"), version="1.0.0", home=str(home), auto_refresh_manifest=False
    )
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("\n".join(manifest) + "\n")
    app.manifest.import_file(str(manifest_file))
    return app


def test_fifty_games(tmp_path):
    app = build(tmp_path)
    timings = {}

    async def timed(name, coro):
        start = time.perf_counter()
        result = await coro
        timings[name] = time.perf_counter() - start
        return result

    async def go():
        found = await timed("discover", app.discover_games(True))
        matches = await timed("match_games", app.match_games())
        keys = [m["key"] for m in matches]

        async def previews():
            return [await app.preview_game(k) for k in keys]

        shown = await timed("preview_each", previews())
        plan = await timed("plan_sync", app.plan_sync(keys))
        for key in keys:
            app.game_configs.update(key, {"enabled": True})
        await timed("qam_summary", app.qam_summary())
        await timed("health_checks", app.health_checks(False))

        async def push_all():
            return [await app.sync_push(k) for k in keys]

        pushed = await timed("first_push_all", push_all())
        idle = await timed("idle_pass", app.idle_pass())
        return found, matches, shown, plan, pushed, idle

    found, matches, shown, plan, pushed, idle = asyncio.run(go())
    print("\n50-game timings (seconds):")
    for name, seconds in timings.items():
        print(f"  {name:16s} {seconds:7.2f}  (budget {BUDGET_SECONDS[name]})")
    assert len(found["games"]) == GAMES
    assert all(m["gameKey"] for m in matches)
    assert all(p["totalFiles"] == 5 for p in shown)
    assert {p["action"] for p in plan} == {"push"}
    assert {r["status"] for r in pushed} == {"published"}
    assert len(idle) == GAMES and {o["status"] for o in idle} == {"ok"}
    for name, seconds in timings.items():
        assert seconds < BUDGET_SECONDS[name], f"{name} took {seconds:.1f} s"
