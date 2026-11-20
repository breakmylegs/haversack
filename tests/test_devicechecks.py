"""Device checks inside the plugin (ADR-0062). Synthetic folders and names only."""

import asyncio
import json
import os

import pytest

from keepsake import devicechecks as dc
from keepsake import power
from keepsake.replication import discovery, link, netinfo
from test_replication_devices import make_app  # noqa: F401 - the app fixture


def context(tmp_path, **overrides):
    library = tmp_path / "home" / "Games"
    library.mkdir(parents=True, exist_ok=True)
    compat = tmp_path / "steam" / "steamapps" / "compatdata"
    compat.mkdir(parents=True, exist_ok=True)
    values = {
        "home": str(tmp_path / "home"),
        "proc_root": str(tmp_path / "proc"),
        "sys_root": str(tmp_path / "sys"),
        "library": str(library),
        "places": {"compatdata": str(compat), "tools": str(tmp_path / "steam" / "compatibilitytools.d")},
        "work_dir": str(tmp_path / "work"),
    }
    values.update(overrides)
    os.makedirs(values["work_dir"], exist_ok=True)
    return dc.Context(**values)


def run(check_id, ctx):
    return asyncio.run(dc.run(check_id, ctx))


@pytest.mark.skipif(not link.available(), reason="this OpenSSL has no TLS-PSK")
def test_the_encrypted_link_check_runs_a_real_handshake(tmp_path):
    result = run("link", context(tmp_path))
    assert result["status"] == "pass" and "ECDHE-PSK-CHACHA20-POLY1305" in result["found"]
    assert result["details"]["python"] and result["details"]["openssl"]


def test_without_tls_psk_the_link_check_fails_plainly(tmp_path, monkeypatch):
    monkeypatch.setattr(link, "available", lambda: False)
    result = run("link", context(tmp_path))
    assert result["status"] == "fail" and "no TLS-PSK" in result["found"]


def test_addresses(tmp_path, monkeypatch):
    monkeypatch.setattr(netinfo, "local_addresses", lambda proc_root: [{"address": "127.0.0.1", "kind": "lan"}])
    assert run("addresses", context(tmp_path))["status"] == "pass"
    monkeypatch.setattr(netinfo, "local_addresses", lambda proc_root: [])
    result = run("addresses", context(tmp_path))
    assert result["status"] == "fail" and "connect to Wi-Fi" in result["found"]


def test_mdns_passes_only_when_its_own_answer_comes_back(tmp_path, monkeypatch):
    seen = {}

    class Transport:
        def close(self):
            seen["closed"] = True

    async def responder(device_id, name, port):
        seen["id"] = device_id
        return Transport()

    async def browse_answered(own_id, seconds):
        return [{"id": seen["id"]}]

    async def browse_silent(own_id, seconds):
        return []

    monkeypatch.setattr(discovery, "start_responder", responder)
    monkeypatch.setattr(discovery, "browse", browse_answered)
    assert run("mdns", context(tmp_path))["status"] == "pass" and seen["closed"]
    monkeypatch.setattr(discovery, "browse", browse_silent)
    assert run("mdns", context(tmp_path))["status"] == "warn"

    async def busy(*a):
        raise OSError(98, "Address already in use")

    monkeypatch.setattr(discovery, "start_responder", busy)
    result = run("mdns", context(tmp_path))
    assert result["status"] == "fail" and "Address already in use" in result["found"]


@pytest.mark.skipif(os.name == "nt", reason="the firewall check is for Linux")
def test_firewall_reads_the_default_zone(tmp_path, monkeypatch):
    (tmp_path / "proc" / "77").mkdir(parents=True)
    (tmp_path / "proc" / "77" / "comm").write_text("firewalld\n")
    conf = tmp_path / "firewalld.conf"
    conf.write_text("DefaultZone=FedoraWorkstation\n")
    zones = tmp_path / "zones"
    zones.mkdir()
    (zones / "FedoraWorkstation.xml").write_text(
        '<zone><port port="1025-65535" protocol="tcp"/><port port="1025-65535" protocol="udp"/></zone>'
    )
    monkeypatch.setattr(dc, "FIREWALLD_CONF", str(conf))
    monkeypatch.setattr(dc, "ZONE_DIRS", (str(zones),))
    result = run("firewall", context(tmp_path))
    assert result["status"] == "pass" and result["details"]["zone"] == "FedoraWorkstation"
    (zones / "FedoraWorkstation.xml").write_text('<zone><service name="ssh"/></zone>')
    assert run("firewall", context(tmp_path))["status"] == "warn"


def test_firewall_logic_on_any_platform():
    ports, services = dc._zone_ports('<port port="1025-65535" protocol="tcp"/><service name="mdns"/>')
    assert dc._covers(ports, 47110, "tcp") and not dc._covers(ports, 47110, "udp") and "mdns" in services
    assert not dc._covers({"22/tcp"}, 47110, "tcp")


def test_wake_on_lan_says_wifi_only_is_expected(tmp_path):
    net = tmp_path / "sys" / "class" / "net" / "wlan0"
    (net / "device").mkdir(parents=True)
    (net / "wireless").mkdir()
    (net / "address").write_text("aa:bb:cc:dd:ee:01\n")
    result = run("wake", context(tmp_path))
    assert result["status"] == "pass" and "Wi-Fi only" in result["found"]
    assert "aa:bb" not in json.dumps(result)  # the hardware address is never shown


def test_the_file_system_check_copies_through_the_real_engine(tmp_path):
    result = run("filesystems", context(tmp_path))
    assert result["status"] == "pass", result["found"]
    (row,) = result["details"]["places"]
    assert row["exact"] and row["times"] and row["place"] == "~/Games"
    assert os.listdir(tmp_path / "home" / "Games") == []  # nothing left behind
    assert not [n for n in os.listdir(tmp_path / "work") if n.startswith(dc.TEST_PREFIX)]
    if os.name == "posix":
        assert row["modes"] and row["links"]


def test_the_file_system_check_needs_a_library(tmp_path):
    result = run("filesystems", context(tmp_path, library=str(tmp_path / "missing")))
    assert result["status"] == "fail" and "Settings, Install" in result["found"]


def test_sleep(tmp_path, monkeypatch):
    class Guard:
        def __init__(self, held, fds):
            self._held, self.fds, self.windows, self.problem = held, fds, False, "no bus"

        def acquire(self, why):
            return self._held

        def release(self):
            self.released = True

    monkeypatch.setattr(dc, "SleepGuard", lambda: Guard(True, [3, 4]))
    assert run("sleep", context(tmp_path))["status"] == "pass"
    monkeypatch.setattr(dc, "SleepGuard", lambda: Guard(False, []))
    assert run("sleep", context(tmp_path))["status"] == "fail"
    if os.name != "nt":
        monkeypatch.setattr(dc, "SleepGuard", lambda: Guard(True, [3]))
        assert run("sleep", context(tmp_path))["status"] == "warn"


def test_battery(tmp_path, monkeypatch):
    monkeypatch.setattr(power, "battery_present", lambda: True)
    monkeypatch.setattr(power, "battery_state", lambda: (64, True))
    result = run("battery", context(tmp_path))
    assert result["status"] == "pass" and "64%" in result["found"] and "charger" in result["found"]
    monkeypatch.setattr(power, "battery_state", lambda: (None, None))
    assert run("battery", context(tmp_path))["status"] == "warn"
    monkeypatch.setattr(power, "battery_present", lambda: False)
    assert "No battery" in run("battery", context(tmp_path))["found"]


def test_steam_folders(tmp_path):
    ctx = context(tmp_path)
    assert run("steam", ctx)["status"] == "pass"
    assert os.listdir(ctx.places["compatdata"]) == []  # the probe folder is gone
    missing = context(tmp_path, places={"compatdata": str(tmp_path / "nope")})
    assert run("steam", missing)["status"] == "fail"


def test_hashing_speed(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "HASH_BYTES", 8 * 1024 * 1024)
    result = run("hashing", context(tmp_path))
    assert result["status"] == "pass" and result["details"]["megabytesPerSecond"] > 0


class Peers:
    def __init__(self, peers):
        self._peers = peers

    def list(self):
        return self._peers


class Links:
    def __init__(self, peers):
        self.store = Peers(peers)
        self.me = link.Identity("device-aaaa-0001", "A")


def test_the_two_device_checks_skip_without_a_paired_device(tmp_path):
    for check in ("speed", "find"):
        assert run(check, context(tmp_path))["status"] == "skip"
        assert run(check, context(tmp_path, links=Links([])))["status"] == "skip"


def test_link_speed_against_the_other_handheld(tmp_path):
    class Connection:
        async def ping(self):
            return 2.0

        async def request_blob(self, message, max_size=0):
            return await dc.serve_speed(None, message)

        async def close(self):
            pass

    def connect_for(_peer):
        async def connect():
            return Connection()

        return connect

    ctx = context(tmp_path, links=Links([{"id": "device-bbbb-0002", "name": "B", "address": "192.168.1.30:47110"}]))
    ctx.connect_for = connect_for
    result = run("speed", ctx)
    assert result["status"] in ("pass", "warn") and "MB/s" in result["found"]
    assert result["details"]["rttMs"] == 2.0 and "192.168" not in json.dumps(result)


def test_the_speed_server_bounds_what_it_sends():
    header, data = asyncio.run(dc.serve_speed(None, {"size": 3 * 1024 * 1024 + 5}))
    assert len(data) == 3 * 1024 * 1024 + 5 and header == {"size": len(data)}
    for bad in (0, -1, dc.SPEED_BYTES + 1, "big"):
        assert asyncio.run(dc.serve_speed(None, {"size": bad}))["type"] == "error"


def test_find_the_other_handheld(tmp_path, monkeypatch):
    peer = {"id": "device-bbbb-0002", "name": "B", "address": ""}
    ctx = context(tmp_path, links=Links([peer]))

    async def found_peer(own_id, seconds):
        return [{"id": "device-bbbb-0002"}]

    async def found_none(own_id, seconds):
        return []

    monkeypatch.setattr(discovery, "browse", found_peer)
    assert run("find", ctx)["status"] == "pass"
    monkeypatch.setattr(discovery, "browse", found_none)
    assert run("find", ctx)["status"] == "fail"


def test_a_check_that_breaks_is_a_failed_check(tmp_path, monkeypatch):
    async def broken(_ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(dc.BY_ID["battery"], "run", broken)
    result = run("battery", context(tmp_path))
    assert result["status"] == "fail" and "RuntimeError" in result["found"]
    with pytest.raises(ValueError):
        run("nope", context(tmp_path))


def test_paths_are_shown_without_names(tmp_path):
    home = str(tmp_path / "home")
    assert dc.tilde(os.path.join(home, "Games"), home) == "~/Games"
    assert dc.tilde("/run/media/deck/MyCardLabel", home) == "<SD card>"
    assert dc.tilde(str(tmp_path / "elsewhere"), home) == "<another folder>"


def test_the_summary_is_short_and_names_each_check():
    results = [{"id": "link", "status": "pass", "found": "The encrypted link works."}]
    text = dc.summary("0.26.0-beta.1", results, "Test handheld model")
    assert text.splitlines() == [
        "Keepsake 0.26.0-beta.1 device checks, Test handheld model",
        "link: OK The encrypted link works.",
    ]


def test_the_app_exports_one_redacted_file(make_app, monkeypatch):  # noqa: F811
    async def scenario():
        app = make_app("a")
        await app.start()
        try:
            await app.set_setting("deviceName", "Secret Test Name")
            with pytest.raises(ValueError, match="run the checks first"):
                await app.device_checks_export()
            listed = await app.device_checks()
            assert [c["id"] for c in listed["checks"]] == [c.id for c in dc.CHECKS] and listed["results"] == []
            outcome = await app.device_check_run("battery")
            assert outcome["id"] == "battery" and outcome["status"] in dc.STATUSES
            exported = await app.device_checks_export()
            assert exported["summary"].startswith("Keepsake 0.9.0 device checks")
            path = os.path.join(app.paths.settings_dir, exported["file"])
            text = open(path, encoding="utf-8").read()
            assert "Secret Test Name" not in text and "Secret Test Name" not in exported["summary"]
            assert json.loads(text)["results"][0]["id"] == "battery"
        finally:
            await app.stop()

    asyncio.run(scenario())


def test_a_copy_that_is_not_exact_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "_digest", lambda path: path)  # every copy differs from its source
    result = run("filesystems", context(tmp_path))
    assert result["status"] == "fail" and "not exact" in result["found"]


def test_addresses_that_cannot_be_listened_on_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(netinfo, "local_addresses", lambda proc_root: [{"address": "127.0.0.1", "kind": "lan"}])

    async def refuse(*a, **k):
        raise OSError(99, "Cannot assign requested address")

    monkeypatch.setattr(dc.asyncio, "start_server", refuse)
    result = run("addresses", context(tmp_path))
    assert result["status"] == "fail" and "cannot listen" in result["found"]


def test_another_device_answering_is_not_the_paired_one(tmp_path, monkeypatch):
    ctx = context(tmp_path, links=Links([{"id": "device-bbbb-0002", "name": "B", "address": ""}]))

    async def someone_else(own_id, seconds):
        return [{"id": "device-cccc-0003"}]

    monkeypatch.setattr(discovery, "browse", someone_else)
    assert run("find", ctx)["status"] == "warn"


def test_an_unwritable_prefix_folder_fails(tmp_path, monkeypatch):
    ctx = context(tmp_path)

    def refuse(path, *a):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(dc.os, "mkdir", refuse)
    result = run("steam", ctx)
    assert result["status"] == "fail" and "cannot write" in result["found"]
