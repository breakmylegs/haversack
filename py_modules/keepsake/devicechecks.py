"""Device checks: the device run's measurements, inside the plugin (ADR-0062).

Each check runs on this device from a button in Settings, Diagnostics, and reports pass, warn,
fail or skip, with what it found in plain words. Nothing here needs SSH, a terminal or the
laptop. Findings are redacted as they are made: no device or network names, no addresses,
no hardware addresses and no paths outside ``~``, so the exported file and the on-screen
summary can be sent as they are (principle 12).

Checks marked ``both`` need the other handheld: paired, on, and with its listener on.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import re
import secrets
import shutil
import stat
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from . import power
from .replication import discovery, link, netinfo, policy, transfer
from .replication import manifest as mf
from .replication.service import firewalld_running
from .replication.sleepguard import SleepGuard
from .replication.source import Shares

STATUSES = ("pass", "warn", "fail", "skip")
SPEED_BYTES = 16 * 1024 * 1024  # one link speed request
HASH_BYTES = 512 * 1024 * 1024
TEST_PREFIX = ".keepsake-device-check-"
FIREWALLD_CONF = "/etc/firewalld/firewalld.conf"
ZONE_DIRS = ("/etc/firewalld/zones", "/usr/lib/firewalld/zones")
EXPECTED_NO_LINKS = ("vfat", "exfat", "msdos", "ntfs", "ntfs3", "fuseblk")


@dataclass
class Context:
    home: str
    proc_root: str
    sys_root: str
    library: str
    places: dict[str, str]
    work_dir: str
    links: Any = None  # replication.service.Links, when Replication runs
    connect_for: Callable[[str], Callable[[], Awaitable[Any]]] | None = None
    # Findings only the app can gather (its games, settings and Steam's report), by check id.
    probes: dict[str, Callable[[], Awaitable[dict[str, Any]]]] = field(default_factory=dict)


@dataclass
class Check:
    id: str
    title: str
    needs: str  # "one" or "both"
    checks: str  # what it replaces, for the report
    run: Callable[[Context], Awaitable[dict[str, Any]]] = field(repr=False)


def result(status: str, found: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "found": found, "details": details}


def tilde(path: str, home: str) -> str:
    """A path as the user sees it, with home as ``~`` and an SD card's own name hidden."""
    if re.match(r"^/run/media/", path.replace(os.sep, "/")):
        return "<SD card>"  # a card's label is its owner's choice: never shown
    real, real_home = os.path.realpath(path), os.path.realpath(home)
    if real == real_home or real.startswith(real_home + os.sep):
        return "~" + real[len(real_home) :].replace(os.sep, "/")
    match = re.match(r"^/run/media/(?:[^/]+/)?([^/]+)", real)
    if match:
        return "<SD card>"
    return "<another folder>"


# The encrypted link (A188)


async def check_tls(_ctx: Context) -> dict[str, Any]:
    import ssl

    versions = {"python": sys.version.split()[0], "openssl": ssl.OPENSSL_VERSION}
    if not link.available():
        return result("fail", "This Python has no TLS-PSK, so Replication stays off.", **versions)
    key = secrets.token_bytes(32)
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0, ssl=link.server_context(lambda _i: key))
    port = server.sockets[0].getsockname()[1]
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                "127.0.0.1", port, ssl=link.client_context("device-check", key), server_hostname=None
            ),
            10,
        )
        link.checked_session(writer)
        cipher = writer.get_extra_info("ssl_object").cipher()[0]
        writer.close()
    except (OSError, ssl.SSLError, link.LinkError, TimeoutError) as exc:
        return result("fail", f"The encrypted link did not work: {type(exc).__name__}.", **versions)
    finally:
        server.close()
    return result("pass", f"The encrypted link works ({cipher}, no compression).", cipher=cipher, **versions)


# Addresses, discovery, firewall, Wake-on-LAN (A190, A191)


async def check_addresses(ctx: Context) -> dict[str, Any]:
    addresses = netinfo.local_addresses(ctx.proc_root)
    lan = [a for a in addresses if a["kind"] == "lan"]
    overlay = [a for a in addresses if a["kind"] == "overlay"]
    bindable = 0
    for address in lan + overlay:
        try:
            server = await asyncio.start_server(lambda r, w: w.close(), address["address"], 0)
            server.close()
            bindable += 1
        except OSError:
            pass
    counts = {"homeNetwork": len(lan), "vpn": len(overlay), "listenable": bindable}
    if not lan and not overlay:
        return result("fail", "No home network or VPN address: connect to Wi-Fi and run it again.", **counts)
    if not bindable:
        return result("fail", "Addresses found, but Keepsake cannot listen on any of them.", **counts)
    return result("pass", f"{len(lan)} home network and {len(overlay)} VPN address(es); listening works.", **counts)


async def check_mdns(_ctx: Context) -> dict[str, Any]:
    test_id = f"device-check-{secrets.token_hex(4)}"
    try:
        responder = await discovery.start_responder(test_id, lambda: "check", 1)
    except OSError as exc:
        return result("fail", f"Cannot join the mDNS group beside avahi ({exc.strerror or exc}).", errno=exc.errno)
    try:
        found = await discovery.browse("someone-else", 1.5)
    finally:
        responder.close()
    if any(d["id"] == test_id for d in found):
        return result("pass", "Other devices can find this one on the network.", answered=True)
    return result("warn", "Joined the mDNS group, but its own answer did not come back.", answered=False)


def _zone_ports(xml: str) -> tuple[set[str], set[str]]:
    ports = set(re.findall(r'<port\s+port="([^"]+)"\s+protocol="([a-z]+)"', xml))
    services = set(re.findall(r'<service\s+name="([^"]+)"', xml))
    return {f"{p}/{proto}" for p, proto in ports}, services


def _covers(ports: set[str], number: int, proto: str) -> bool:
    for entry in ports:
        spec, _, kind = entry.partition("/")
        if kind != proto:
            continue
        low, _, high = spec.partition("-")
        if low.isdigit() and int(low) <= number <= int(high or low):
            return True
    return False


async def check_firewall(ctx: Context) -> dict[str, Any]:
    if os.name == "nt":
        return result("skip", "Windows asks about Python the first time the listener starts.")
    if not firewalld_running(ctx.proc_root):
        return result("pass", "No firewall is running on this device.", firewalld=False)
    zone = "public"
    with contextlib.suppress(OSError):
        with open(FIREWALLD_CONF, encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith("DefaultZone="):
                    zone = line.split("=", 1)[1].strip() or zone
    xml = ""
    for folder in ZONE_DIRS:
        with contextlib.suppress(OSError):
            with open(os.path.join(folder, f"{zone}.xml"), encoding="utf-8") as handle:
                xml = handle.read()
                break
    ports, services = _zone_ports(xml)
    tcp = _covers(ports, link.DEFAULT_PORT, "tcp")
    udp = _covers(ports, discovery.PORT, "udp") or "mdns" in services
    details = {"firewalld": True, "zone": zone, "tcp47110": tcp, "udp5353": udp}
    if tcp and udp:
        return result("pass", f"firewalld's {zone} zone already allows Keepsake.", **details)
    return result(
        "warn",
        f"firewalld's {zone} zone may block Keepsake: allow TCP 47110 and UDP 5353 (Health says how).",
        **details,
    )


async def check_wake(ctx: Context) -> dict[str, Any]:
    base = os.path.join(ctx.sys_root, "class", "net")
    wired = wireless = 0
    with contextlib.suppress(OSError):
        for name in os.listdir(base):
            if not os.path.exists(os.path.join(base, name, "device")):
                continue
            if os.path.exists(os.path.join(base, name, "wireless")) or os.path.exists(
                os.path.join(base, name, "phy80211")
            ):
                wireless += 1
            else:
                wired += 1
    shared = len(netinfo.own_macs(ctx.sys_root))
    details = {"wired": wired, "wifi": wireless, "shared": shared}
    if not shared:
        return result("warn", "No adapter to wake was found.", **details)
    if not wired:
        return result("pass", "Wi-Fi only: Wake-on-LAN usually cannot wake this device. That is expected.", **details)
    return result("pass", f"{wired} wired adapter(s): Wake-on-LAN can work if the firmware allows it.", **details)


# File systems (A192)


class _Local:
    """The sending side's handlers, called in process: a copy within this device."""

    def __init__(self, shares: Shares) -> None:
        self.shares = shares

    async def request_blob(self, message: dict[str, Any], max_size: int = 0, timeout: float = 30) -> Any:
        class Session:
            peer_id = "device-check"

        reply = await self.shares.handlers()[message["type"]](Session(), message)
        if isinstance(reply, dict):
            raise link.Refused(str(reply.get("reason")))
        return reply

    async def close(self) -> None:
        return None


def _fs_type(path: str, proc_root: str) -> str:
    best, kind = "", "unknown"
    with contextlib.suppress(OSError):
        with open(os.path.join(proc_root, "self", "mounts"), encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) >= 3:
                    point = parts[1].replace("\\040", " ")
                    if os.path.realpath(path).startswith(point) and len(point) > len(best):
                        best, kind = point, parts[2]
    return kind


def _sample(root: str, with_link: bool) -> None:
    os.makedirs(os.path.join(root, "bin"))
    exe = os.path.join(root, "bin", "game.sh")
    with open(exe, "wb") as handle:
        handle.write(b"#!/bin/sh\n" + os.urandom(2000))
    os.chmod(exe, 0o755)  # noqa: S103 - a synthetic test file: the check is whether its executable bit survives
    with open(os.path.join(root, "data.pak"), "wb") as handle:  # a data chunk, a hole and more data
        handle.write(os.urandom(1000))
        handle.seek(2 * mf.CHUNK)
        handle.write(os.urandom(1000))
    os.utime(exe, ns=(1_600_000_000_000_000_000, 1_600_000_000_123_456_789))
    if with_link:
        os.symlink("data.pak", os.path.join(root, "current.pak"))


async def _round_trip(place: str, ctx: Context) -> dict[str, Any]:
    kind = _fs_type(place, ctx.proc_root)
    plain = kind in EXPECTED_NO_LINKS
    tag = secrets.token_hex(4)
    source = os.path.join(ctx.work_dir, f"{TEST_PREFIX}{tag}-source")
    target = os.path.join(place, f"{TEST_PREFIX}{tag}")
    try:
        await asyncio.to_thread(_sample, source, not plain and os.name == "posix")
        built = await asyncio.to_thread(mf.build, source)
        shares = Shares()
        share = shares.add(source, built, {"device-check"})
        job = transfer.Job(f"check{tag}", "device-check", share.id, built["root"], target)

        async def connect() -> Any:
            return _Local(shares)

        done = await transfer.Receiver(job, connect, retries=0).run()
        if done.state != "done":
            return {"place": tilde(place, ctx.home), "fs": kind, "ok": False, "problem": done.reason}
        copied = os.path.join(target, "data.pak")
        exe = os.path.join(target, "bin", "game.sh")
        same = _digest(copied) == _digest(os.path.join(source, "data.pak"))
        holes = (
            os.name == "posix"
            and getattr(os.stat(copied), "st_blocks", 0) * 512 < os.path.getsize(copied) - mf.CHUNK // 2
        )
        modes = os.name == "posix" and stat.S_IMODE(os.stat(exe).st_mode) == 0o755
        times = os.stat(exe).st_mtime_ns == os.stat(os.path.join(source, "bin", "game.sh")).st_mtime_ns
        links = os.path.islink(os.path.join(target, "current.pak"))
        return {
            "place": tilde(place, ctx.home),
            "fs": kind,
            # Windows keeps neither POSIX modes nor links; on Linux they must survive unless the card cannot hold them.
            "ok": same and times and (plain or os.name != "posix" or (links and modes)),
            "exact": same,
            "times": times,
            "modes": modes,
            "links": links,
            "holes": holes,
            "expectedPlain": plain,
        }
    finally:
        for path in (source, target, transfer.staging_for(target, f"check{tag}")):
            # Only the folders this check made, each named with TEST_PREFIX.
            if os.path.basename(path).startswith((TEST_PREFIX, transfer.STAGING_PREFIX)) and os.path.isdir(path):
                with contextlib.suppress(OSError):
                    shutil.rmtree(path)


def _digest(path: str) -> str:
    return mf.hash_file(path)[0]


def _sd_cards(home: str) -> list[str]:
    user = os.path.basename(os.path.realpath(home))
    cards = []
    for base in (f"/run/media/{user}", "/run/media"):
        with contextlib.suppress(OSError):
            for name in sorted(os.listdir(base)):
                path = os.path.join(base, name)
                if os.path.isdir(path) and os.access(path, os.W_OK) and name != user:
                    cards.append(path)
    return cards[:3]


async def check_file_systems(ctx: Context) -> dict[str, Any]:
    places = [p for p in (ctx.library, *_sd_cards(ctx.home)) if p and os.path.isdir(p)]
    if not places:
        return result("fail", "The game library folder was not found: set it in Settings, Install.")
    rows = [await _round_trip(place, ctx) for place in places]
    bad = [r for r in rows if not r["ok"]]
    summary = "; ".join(
        f"{r['place']} ({r['fs']}): "
        + (
            "exact copy"
            + (", modes, links" if r.get("links") else "")
            + (", holes kept" if r.get("holes") else ", no holes")
            if r["ok"]
            else f"failed: {r.get('problem') or 'the copy was not exact'}"
        )
        for r in rows
    )
    return result("fail" if bad else "pass", summary, places=rows)


# Sleep and battery (A193, A194)


async def check_sleep(_ctx: Context) -> dict[str, Any]:
    guard = SleepGuard()
    held = guard.acquire("Keepsake device check")
    count = len(guard.fds) if guard.fds else (1 if guard.windows else 0)
    guard.release()
    if not held:
        return result("fail", guard.problem or "The device would not stay awake for a transfer.")
    if count < 2 and os.name != "nt":
        return result("warn", "Only one of the two sleep locks was granted.", locks=count)
    return result("pass", "The device stays awake during transfers and gives them time before sleep.", locks=count)


async def check_battery(_ctx: Context) -> dict[str, Any]:
    present = power.battery_present()
    percent, mains = power.battery_state()
    if present is False:
        return result("pass", "No battery: on mains power, so transfers never wait for the battery.", battery=False)
    if percent is None:
        return result("warn", "The battery level could not be read: transfers will not wait for it.", battery=present)
    plugged = "on the charger" if mains else "on battery" if mains is False else "charger state unknown"
    return result("pass", f"Battery {percent}%, {plugged}.", percent=percent, mains=mains)


# Steam's folders (A195)


async def check_steam_folders(ctx: Context) -> dict[str, Any]:
    compat = ctx.places.get("compatdata", "")
    tools = ctx.places.get("tools", "")
    if not compat or not os.path.isdir(compat):
        return result("fail", "Steam's compatdata folder was not found.")
    probe = os.path.join(compat, f"{TEST_PREFIX}{secrets.token_hex(4)}")
    try:
        os.mkdir(probe)
        os.rmdir(probe)
    except OSError as exc:
        return result("fail", f"Keepsake cannot write in Steam's compatdata folder ({exc.strerror}).")
    tool_note = (
        "compatibilitytools.d exists"
        if os.path.isdir(tools)
        else "compatibilitytools.d does not exist yet (made when needed)"
    )
    return result("pass", f"Steam's prefix folder is writable; {tool_note}.", tools=os.path.isdir(tools))


# Speed (the slice 16 measurements)


async def check_hashing(_ctx: Context) -> dict[str, Any]:
    block = os.urandom(mf.CHUNK)

    def work() -> float:
        digest = hashlib.sha256()
        started = time.perf_counter()
        for _ in range(HASH_BYTES // len(block)):
            digest.update(block)
        return time.perf_counter() - started

    seconds = await asyncio.to_thread(work)
    rate = HASH_BYTES / seconds / 1_000_000
    return result("pass", f"Checking files runs at {rate:.0f} MB/s.", megabytesPerSecond=round(rate))


def _peer(ctx: Context) -> dict[str, Any] | None:
    if ctx.links is None:
        return None
    peers = ctx.links.store.list()
    return peers[0] if peers else None


async def check_link_speed(ctx: Context) -> dict[str, Any]:
    peer = _peer(ctx)
    if peer is None or ctx.connect_for is None:
        return result("skip", "Pair the other handheld first (Devices), with its listener on.")
    try:
        connection = await asyncio.wait_for(ctx.connect_for(peer["id"])(), 10)
    except (link.LinkError, OSError, TimeoutError):
        return result("fail", "The other device did not answer: switch on its listener, on the same network.")
    try:
        rtt = min([await connection.ping() for _ in range(3)])

        async def one() -> int:
            _h, data = await connection.request_blob({"type": "speed", "size": SPEED_BYTES}, max_size=SPEED_BYTES)
            return len(data)

        started = time.perf_counter()
        received = 0
        for _ in range(4):
            received += await one()
        seconds = time.perf_counter() - started
    except link.Refused:
        return result("fail", "The other device runs an older Keepsake: update both, then run it again.")
    except (link.LinkError, OSError) as exc:
        return result("fail", f"The link dropped during the test ({type(exc).__name__}).")
    finally:
        await connection.close()
    rate = received / seconds / 1_000_000
    address = str(peer.get("address") or "")
    verdict = policy.link_verdict(rate, rtt, overlay=address.startswith("100."))
    status = "warn" if verdict["slow"] else "pass"
    text = f"{rate:.0f} MB/s with one stream, {rtt:.0f} ms round trip." + (
        f" {verdict['message']}" if verdict["message"] else ""
    )
    return result(status, text, megabytesPerSecond=round(rate, 1), rttMs=round(rtt, 1), slow=verdict["slow"])


async def check_find(ctx: Context) -> dict[str, Any]:
    peer = _peer(ctx)
    if peer is None:
        return result("skip", "Pair the other handheld first (Devices), with its listener on.")
    found = await discovery.browse(ctx.links.me.device_id, 2.0)
    if any(d["id"] == peer["id"] for d in found):
        return result("pass", "The other handheld answers Find devices.", devices=len(found))
    if found:
        return result("warn", "Other Keepsake devices answered, but not the paired one.", devices=len(found))
    return result(
        "fail", "No device answered: on the other one, switch on Let other devices reach this one.", devices=0
    )


async def check_remote_shortcuts(ctx: Context) -> dict[str, Any]:
    """Games you can stream from another device: Steam Remote Play's entries (ADR-0064). No device names."""
    probe = ctx.probes.get("remote-shortcuts")
    if probe is None:
        return result("skip", "Switch on the Saves module, then run it again.")
    found = await probe()
    if found.get("reportAt") is None:
        return result("skip", "Steam has not reported its library yet: open the Games page once, then run it again.")
    counts = {k: found[k] for k in ("local", "remote", "unsure", "hidden", "cameBack")}
    clashes = list(found["clashes"])
    text = (
        f"{found['local']} shortcuts installed here, {found['remote']} games you can stream from another device"
        + (f", {found['unsure']} not sure" if found["unsure"] else "")
        + (f", {found['hidden']} hidden by a tidy-up" if found["hidden"] else "")
        + (f", {found['cameBack']} came back after hiding" if found["cameBack"] else "")
        + "."
        + (f" Also installed here: {', '.join(clashes[:5])}." if clashes else "")
    )
    if found["syncedOnCopy"]:
        names = ", ".join(found["syncedOnCopy"][:5])
        return result("fail", f"{text} Synced games Steam says stream: {names}.", clashes=len(clashes), **counts)
    status = "warn" if found["cameBack"] else "pass"
    return result(status, text, clashes=len(clashes), **counts)


async def check_smb_find(ctx: Context) -> dict[str, Any]:
    """Find shares on my network (ADR-0066): which ways of finding SMB servers answer here. No names reported."""
    probe = ctx.probes.get("smb-find")
    if probe is None:
        return result("skip", "Switch on the Installer module, then run it again.")
    found = await probe()
    methods = found["methods"]
    labels = {"mdns": "mDNS", "netbios": "NetBIOS", "wsd": "WS-Discovery"}
    parts = [
        f"{labels[k]} {v if isinstance(v, int) else v.replace('error: ', 'not available: ')}"
        for k, v in methods.items()
    ]
    count = len(found["servers"])
    text = f"{count} Windows share servers found ({', '.join(parts)})."
    details = {"servers": count, **{k: v if isinstance(v, int) else "error" for k, v in methods.items()}}
    if count:
        return result("pass", text, **details)
    if all(isinstance(v, str) for v in methods.values()):
        return result("fail", f"{text} This device could not send the searches.", **details)
    return result(
        "warn",
        f"{text} If you have a NAS or a PC sharing folders, check it is on and on the same network; typing its "
        "address still works.",
        **details,
    )


async def check_network_iso(ctx: Context) -> dict[str, Any]:
    """Installing straight from a network ISO (ADR-0067): in-place mounting here, and a loop test on a share.

    Replaces the SSH ``--loop-test`` step of ``network_mount_probe.py``. Paths and share names are never reported.
    """
    probe = ctx.probes.get("network-iso")
    if probe is None:
        return result("skip", "Switch on the Installer module, then run it again.")
    found = await probe()
    parts = [
        "fusermount3 " + ("present" if found["fusermount3"] else "missing"),
        "/dev/fuse " + ("usable" if found["devFuse"] else "not usable"),
        "in place "
        + (
            "ready"
            if found["inPlace"] is None
            else "off until fusermount3 is approved"
            if not found["approved"]
            else "not available"
        ),
    ]
    details = {k: found[k] for k in ("udisks", "fusermount3", "devFuse", "approved")}
    iso = found["iso"]
    if not found["udisks"]:
        return result("fail", "udisksctl is missing, so no ISO can be opened. " + ", ".join(parts) + ".", **details)
    if iso is None:
        return result(
            "skip",
            "No ISO was found on a mounted network share, so the loop test did not run ("
            + ", ".join(parts)
            + "). Mount a share with an ISO on it (for example, open it in Desktop Mode's file manager), then run "
            "this again.",
            **details,
        )
    details["fstype"] = iso["fstype"]
    if iso["error"] is None:
        return result("pass", f"An ISO on a {iso['fstype']} share opens in place. " + ", ".join(parts) + ".", **details)
    return result(
        "warn",
        f"An ISO on a {iso['fstype']} share could not be opened in place, so Keepsake copies it first. "
        + ", ".join(parts)
        + ".",
        **details,
    )


async def check_desktop_app(ctx: Context) -> dict[str, Any]:
    """Desktop app ready (ADR-0068): both entries for this version, the tray's python3, and a session bus."""
    probe = ctx.probes.get("desktop-app")
    if probe is None:
        return result("skip", "Switch on the Desktop module in Settings, Modules, then run it again.")
    found = await probe()
    problems = [f"{name}: {', '.join(issues)}" for name, issues in found["entries"].items() if issues]
    if not found["python3"]:
        problems.append("python3 is missing, so the tray cannot run")
    if not found["sessionBus"]:
        problems.append("no desktop session bus was found (normal in Gaming Mode: run this in Desktop Mode)")
    details = {
        "entries": not any(found["entries"].values()),
        "python3": found["python3"],
        "sessionBus": found["sessionBus"],
        "page": found["page"],
    }
    if not problems and found["page"]:
        return result(
            "pass",
            "Both Desktop Mode entries are there for this version; python3 and the session bus are ready.",
            **details,
        )
    status = "warn" if found["python3"] and not any(found["entries"].values()) else "fail"
    return result(status, "; ".join(problems) or "The Desktop Mode page is not running.", **details)


async def check_session_sources(ctx: Context) -> dict[str, Any]:
    """Session stats sources (ADR-0069): which readings this handheld gives the Advisor's session record."""
    probe = ctx.probes.get("session-sources")
    if probe is None:
        return result("skip", "Switch on the Advisor module, then run it again.")
    found = await probe()
    labels = {
        "frameRate": "frame rate",
        "socketPower": "APU power",
        "cpuPower": "CPU power",
        "gpuPower": "GPU power",
        "battery": "battery",
        "temperatures": "temperatures",
        "load": "GPU load",
    }
    have = [labels[k] for k in labels if found.get(k)]
    missing = [labels[k] for k in labels if not found.get(k)]
    text = f"Available: {', '.join(have) or 'nothing'}." + (f" Not available: {', '.join(missing)}." if missing else "")
    if not found.get("frameRate"):
        text += (
            " The frame rate comes from Steam's performance overlay while a game runs: play a game for a minute, "
            "then run this again."
        )
        if found.get("mangohudConfig"):
            text += " MangoHud's own logs are also read when it logs."
    details = {k: bool(found.get(k)) for k in labels}
    if not found.get("socketPower") and not found.get("battery"):
        return result("fail", text, **details)
    return result("pass" if found.get("frameRate") else "warn", text, **details)


async def check_see_other(ctx: Context) -> dict[str, Any]:
    """The other handheld can be seen (ADR-0070): any Keepsake device answers Find devices, paired or not."""
    if ctx.links is None:
        return result("skip", "Switch on Replication in Settings, Modules, then run it again.")
    found = await discovery.browse(ctx.links.me.device_id, 2.0)
    if found:
        return result(
            "pass",
            f"{len(found)} other Keepsake {'device answers' if len(found) == 1 else 'devices answer'}.",
            devices=len(found),
        )
    return result(
        "fail",
        "No other Keepsake device answered: on the other one, switch on Let other devices reach this one, on the same "
        "network. Typing its address still works.",
        devices=0,
    )


async def check_device_readings(ctx: Context) -> dict[str, Any]:
    """Device readings (R21 stage 1): which sensors, fans, modes and BIOS details this device exposes."""
    probe = ctx.probes.get("device-readings")
    if probe is None:
        return result("skip", "This build cannot read the device's sensors.")
    found = await probe()
    chips = found.get("chips") or []
    temps = sum(len(c.get("temps", [])) for c in chips)
    fans = [f for c in chips for f in c.get("fans", [])]
    profile = found.get("profile") or {}
    bios = found.get("bios") or {}
    names = [str(c.get("name")) for c in chips]
    details = {
        "chips": names,
        "temps": temps,
        "fans": len(fans),
        "profile": profile.get("current"),
        "choices": profile.get("choices"),
        "bios": bios.get("version"),
        "chargeLimit": (found.get("battery") or {}).get("chargeLimit"),
        "cpu": found.get("cpu"),
    }
    parts = [f"{temps} temperature sensors on {', '.join(names) or 'no chip'}"]
    parts.append(
        f"{len(fans)} fan reading{'s' if len(fans) != 1 else ''}" + (f" ({fans[0]['value']:.0f} RPM)" if fans else "")
    )
    parts.append(
        f"mode {profile['current']} of {', '.join(profile.get('choices') or [])}"
        if profile
        else "no firmware mode exposed"
    )
    parts.append(f"BIOS {bios['version']}" if bios.get("version") else "no BIOS version")
    if not temps:
        return result("fail", "No temperature sensor could be read: " + "; ".join(parts) + ".", **details)
    if not fans or not profile:
        return result(
            "warn",
            "; ".join(parts) + ". Fan or mode control needs these; see docs/research/legion-control.md.",
            **details,
        )
    return result("pass", "; ".join(parts) + ".", **details)


async def check_performance_control(ctx: Context) -> dict[str, Any]:
    """Performance control (R21 stage 2): steamos-manager reachable, what it offers, and a write read back."""
    probe = ctx.probes.get("performance-control")
    if probe is None:
        return result("skip", "Switch on Device in Settings, Modules.")
    found = await probe()
    if not found.get("reachable"):
        return result("fail", f"steamos-manager could not be reached: {found.get('error')}", reachable=False)
    current = found.get("current") or {}
    tdp, profile = current.get("tdp"), current.get("profile")
    details = {
        "tdp": tdp,
        "profile": profile,
        "boost": current.get("boost"),
        "chargeLimit": current.get("chargeLimit"),
        "writeBack": found.get("writeBack"),
        "tools": found.get("tools"),
    }
    parts = []
    if tdp:
        parts.append(f"TDP {tdp['value']} W ({tdp['min']} to {tdp['max']} W)")
    if profile:
        parts.append(f"mode {profile['current']} of {', '.join(profile['available'])}")
    if current.get("boost") is not None:
        parts.append(f"CPU boost {'on' if current['boost'] else 'off'}")
    if current.get("chargeLimit"):
        parts.append(f"charge limit {current['chargeLimit']['value']}")
    if found.get("writeError"):
        return result(
            "fail", "; ".join(parts) + f". A write that changes nothing failed: {found['writeError']}", **details
        )
    if not tdp and not profile:
        return result("warn", "steamos-manager runs but offers no TDP or mode here.", **details)
    if found.get("tools"):
        return result(
            "warn",
            "; ".join(parts) + f". {', '.join(found['tools'])} manages performance, so Keepsake only shows it.",
            **details,
        )
    return result("pass", "; ".join(parts) + f". Written and read back: {found.get('writeBack')}.", **details)


async def check_charge_limit(ctx: Context) -> dict[str, Any]:
    """Battery charge limit (R21 stage 4): who controls the 80 percent limit here, and its state."""
    probe = ctx.probes.get("charge-limit")
    if probe is None:
        return result("skip", "Switch on Device in Settings, Modules.")
    found = await probe()
    firmware = found.get("firmware") or {}
    details = {
        "control": found.get("control"),
        "limited": found.get("limited"),
        "level": found.get("level"),
        "chargeTypes": firmware.get("chargeTypes"),
        "threshold": firmware.get("threshold"),
    }
    state = {True: "on", False: "off", None: "unknown"}[found.get("limited")]
    if found.get("control") == "steamos-manager":
        return result("pass", f"Keepsake can set it through steamos-manager; the limit is {state}.", **details)
    if firmware.get("chargeTypes") or firmware.get("threshold") is not None:
        return result(
            "warn",
            f"The kernel shows the limit ({state}), but steamos-manager does not offer it here, "
            "so Keepsake only shows it. " + str(found.get("where") or ""),
            **details,
        )
    return result("fail", "Neither steamos-manager nor the kernel shows a charge limit on this device.", **details)


TRAY_LIMIT_MS = 200.0


async def check_tray_responsive(ctx: Context) -> dict[str, Any]:
    """Desktop tray responsive (v0.30.1): the tray's D-Bus replies and the page's get_status, each under 200 ms."""
    probe = ctx.probes.get("tray-responsive")
    if probe is None:
        return result("skip", "Run this in Desktop Mode, with the Desktop module on.")
    found = await probe()
    details = {k: found.get(k) for k in ("trayMs", "statusMs", "tray", "page")}
    if not found.get("tray") and found.get("statusMs") is None:
        return result("skip", "No Keepsake tray is running here: run this in Desktop Mode.", **details)
    slow = []
    if found.get("trayMs") is not None and found["trayMs"] > TRAY_LIMIT_MS:
        slow.append(f"the tray took {found['trayMs']:.0f} ms to answer")
    if found.get("statusMs") is not None and found["statusMs"] > TRAY_LIMIT_MS:
        slow.append(f"the plugin took {found['statusMs']:.0f} ms to give its status")
    for key, what in (("trayError", "the tray did not answer"), ("statusError", "the plugin's page did not answer")):
        if found.get(key):
            slow.append(f"{what} ({found[key]})")
    parts = []
    if found.get("trayMs") is not None:
        parts.append(f"tray {found['trayMs']:.0f} ms")
    if found.get("statusMs") is not None:
        parts.append(f"status {found['statusMs']:.0f} ms")
    if slow:
        return result("fail", "; ".join(slow) + ".", **details)
    return result("pass", f"Answering quickly: {', '.join(parts)}.", **details)


_SPEED_BLOCK = b""


async def serve_speed(_session: Any, message: dict[str, Any]) -> Any:
    """The other side of the link speed check: up to 16 MiB of filler, from paired devices only."""
    global _SPEED_BLOCK
    size = message.get("size")
    if not isinstance(size, int) or not 0 < size <= SPEED_BYTES:
        return {"type": "error", "reason": "ask for at most 16 MiB"}
    if not _SPEED_BLOCK:
        _SPEED_BLOCK = os.urandom(1024 * 1024)
    whole, rest = divmod(size, len(_SPEED_BLOCK))
    return {"size": size}, _SPEED_BLOCK * whole + _SPEED_BLOCK[:rest]


CHECKS = [
    Check("link", "Encrypted link", "one", "A188, test_on_device.py", check_tls),
    Check("addresses", "Listening addresses", "one", "A190", check_addresses),
    Check("mdns", "Found on the network", "one", "A190", check_mdns),
    Check("firewall", "Firewall", "one", "A191, firewall-cmd", check_firewall),
    Check("wake", "Wake-on-LAN", "one", "A190", check_wake),
    Check(
        "filesystems",
        "File systems and SD card",
        "one",
        "A192, test_on_device.py (links, modes, holes)",
        check_file_systems,
    ),
    Check("sleep", "Staying awake", "one", "A193, systemd-inhibit --list, test_on_device.py (D-Bus)", check_sleep),
    Check("battery", "Battery", "one", "A194", check_battery),
    Check("steam", "Steam's folders", "one", "A195", check_steam_folders),
    Check("hashing", "Checking speed", "one", "replication_measure.py hash", check_hashing),
    Check(
        "speed", "Link speed to the other handheld", "both", "replication_measure.py send and serve", check_link_speed
    ),
    Check("find", "Finding the other handheld", "both", "A190", check_find),
    Check("see-other", "The other handheld can be seen", "both", "A190, ADR-0070", check_see_other),
    Check(
        "remote-shortcuts", "Games you can stream from another device", "one", "A199 to A201", check_remote_shortcuts
    ),
    Check("smb-find", "Find shares on my network", "one", "A206", check_smb_find),
    Check("network-iso", "Network ISO in place", "one", "A158, network_mount_probe.py --loop-test", check_network_iso),
    Check("desktop-app", "Desktop app ready", "one", "A208, A209", check_desktop_app),
    Check("session-sources", "Session stats sources", "one", "A211, A212", check_session_sources),
    Check("tray-responsive", "Desktop tray responsive", "one", "v0.30.1", check_tray_responsive),
    Check("device-readings", "Device readings", "one", "ADR-0074", check_device_readings),
    Check("performance-control", "Performance control", "one", "ADR-0076", check_performance_control),
    Check("charge-limit", "Battery charge limit", "one", "ADR-0077", check_charge_limit),
]
BY_ID = {c.id: c for c in CHECKS}


async def run(check_id: str, ctx: Context) -> dict[str, Any]:
    check = BY_ID.get(check_id)
    if check is None:
        raise ValueError("there is no such check")
    started = time.time()
    try:
        outcome = await check.run(ctx)
    except Exception as exc:  # noqa: BLE001 - a check that breaks is a failed check, never a crash
        outcome = result("fail", f"The check itself failed ({type(exc).__name__}).")
    return {"id": check.id, "title": check.title, "needs": check.needs, "at": started, **outcome}


def summary(version: str, results: list[dict[str, Any]], model: str) -> str:
    """One short line per check, for the screen and the QR code."""
    letters = {"pass": "OK", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
    lines = [f"Keepsake {version} device checks, {model}"]
    for item in results:
        lines.append(f"{item['id']}: {letters.get(item['status'], item['status'])} {item['found'][:90]}")
    return "\n".join(lines)


def model_name(sys_root: str = "/sys") -> str:
    """The device model, such as a handheld's product name. Not personal: shared by every unit."""
    for name in ("product_name", "product_family"):
        with contextlib.suppress(OSError):
            with open(os.path.join(sys_root, "class", "dmi", "id", name), encoding="utf-8", errors="replace") as handle:
                text = re.sub(r"[^\w .()-]", "", handle.read()).strip()
                if text:
                    return text[:40]
    return "unknown device"
