from helpers import write_fake_proc
from keepsake.procs import SHORTCUT_GAMEID_FLAG, find_game_processes, match_reason, read_proc

APPID = 4171510507
COMPAT = f"/home/u/.local/share/Steam/steamapps/compatdata/{APPID}"


def build_tree(root):
    # 1 init, 100 steam (ancestor of plugin), 150 decky, 160 plugin (self)
    write_fake_proc(root, 1, 0, "systemd", uid=0)
    write_fake_proc(root, 100, 1, "steam", env={"SteamGameId": str(APPID)})
    write_fake_proc(root, 150, 100, "PluginLoader")
    write_fake_proc(root, 160, 150, "Keepsake", env={"STEAM_COMPAT_DATA_PATH": COMPAT})
    # Game tree: reaper 200 -> proton 210 -> game.exe 220 -> child 230 (no env)
    write_fake_proc(root, 200, 100, "reaper", env={"SteamGameId": str((APPID << 32) | SHORTCUT_GAMEID_FLAG)})
    write_fake_proc(root, 210, 200, "python3", env={"STEAM_COMPAT_DATA_PATH": COMPAT})
    write_fake_proc(root, 220, 210, "game.exe", env={"STEAM_COMPAT_DATA_PATH": COMPAT + "/"})
    write_fake_proc(root, 230, 220, "crashhandler.exe")
    # Another game, and a process of another user with matching env
    write_fake_proc(root, 300, 100, "other.exe", env={"STEAM_COMPAT_DATA_PATH": "/x/compatdata/999"})
    write_fake_proc(root, 400, 1, "foreign", uid=1001, env={"STEAM_COMPAT_DATA_PATH": COMPAT})


def test_read_proc_parses_comm_with_spaces_and_parens(tmp_path):
    write_fake_proc(str(tmp_path), 5, 1, "Game (x) y", starttime=777, env={"SteamAppId": "10", "PATH": "/bin"})
    info = read_proc(5, str(tmp_path))
    assert info is not None
    assert info.comm == "Game (x) y"
    assert info.ppid == 1 and info.starttime == 777 and info.uid == 1000
    assert info.env == {"SteamAppId": "10"}


def test_read_proc_missing(tmp_path):
    assert read_proc(99, str(tmp_path)) is None


def test_find_game_processes_selects_tree_only(tmp_path):
    build_tree(str(tmp_path))
    procs = find_game_processes(APPID, proc_root=str(tmp_path), uid=1000, self_pid=160)
    assert [p.pid for p in procs] == [200, 210, 220, 230]
    reasons = {p.pid: p.match for p in procs}
    assert reasons[200] == "steam-game-id"
    assert reasons[210] == "compat-id"
    assert reasons[230] == "descendant"


def test_never_selects_self_or_ancestors(tmp_path):
    build_tree(str(tmp_path))
    pids = {p.pid for p in find_game_processes(APPID, proc_root=str(tmp_path), uid=1000, self_pid=160)}
    assert not pids & {1, 100, 150, 160}


def test_other_users_ignored(tmp_path):
    build_tree(str(tmp_path))
    pids = {p.pid for p in find_game_processes(APPID, proc_root=str(tmp_path), uid=1000, self_pid=160)}
    assert 400 not in pids


def test_signed_appid_matches_unsigned_env(tmp_path):
    build_tree(str(tmp_path))
    signed = APPID - 2**32
    pids = [p.pid for p in find_game_processes(signed, proc_root=str(tmp_path), uid=1000, self_pid=160)]
    assert pids == [200, 210, 220, 230]


def test_match_reason_compat_path(tmp_path):
    write_fake_proc(str(tmp_path), 7, 1, "g", env={"STEAM_COMPAT_DATA_PATH": "/a/b"})
    info = read_proc(7, str(tmp_path))
    assert info is not None
    assert match_reason(info, 1, compat_path="/a/b") == "compat-path"
    assert match_reason(info, 1) == ""
