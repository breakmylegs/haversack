"""Controller reconnect help, the parts that need no root (R22, ADR-0082).

Some non-official and clone Bluetooth Classic (BR/EDR) controllers pair once and then never
reconnect with their normal button. The research (BlueZ issues 2678, 2679 and 2380) found five
faults, F1 to F5, seen as outcomes O1 to O7. This file holds the generic parts:

- addresses, and the "not from a registered manufacturer" flag (information only);
- the user's help rules, keyed by adapter and device address, with an append-only action log
  and a dry-run switch;
- the journal read (``journalctl``, System Binary Register) and its failure signs;
- the diagnosis classifier.

Nothing here infers what a device is from its name, class or modalias: clones copy them. Help
acts only on devices the user turned it on for. Bluetooth LE controllers are out of scope.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable
from typing import Any

MAX_RULES = 16
JOURNAL_TIMEOUT = 5.0
JOURNAL_LINES = 400
_MAC = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")
_ANY_MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")


class ReconnectError(Exception):
    pass


def normal_mac(value: Any) -> str | None:
    """An address as ``AA:BB:CC:DD:EE:FF``, or None. Dashes are accepted; zero and broadcast are not."""
    text = str(value or "").strip().upper().replace("-", ":")
    if not _MAC.match(text) or text in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        return None
    return text


def masked(mac: str) -> str:
    """For logs, the action log and exports: only the last two bytes, enough to tell two pads apart."""
    return "XX:XX:XX:XX:" + mac[-5:] if normal_mac(mac) else "unknown"


def unregistered_prefix(mac: str) -> bool:
    """True when the first byte has the group bit (0x01) or the locally administered bit (0x02) set.

    IEEE assigns manufacturer prefixes (MA-L, MA-M, MA-S) with both bits clear, so such an address
    cannot come from one. Many clones use one. Information for the user only: never acted on.
    """
    address = normal_mac(mac)
    return address is not None and int(address[:2], 16) & 0x03 != 0


def rule_key(adapter: str, mac: str) -> str:
    return f"{adapter}/{mac}"


class Rules:
    """The devices the user turned help on for, in the settings folder (``reconnect-help.json``).

    ``{"rules": {"ADAPTER/MAC": {adapter, mac, label, commit, fullMode, added}},
    "last": {key: diagnosis}, "suggest": {key: {reason, at}}, "dryRun": bool}``.
    The action log is a separate append-only file of JSON lines next to it.
    """

    def __init__(self, path: str, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.log_path = os.path.join(os.path.dirname(path) or ".", "reconnect-actions.log")
        self.clock = clock

    def _load(self) -> dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        rules = {}
        for key, rule in dict(data.get("rules") or {}).items():
            adapter, mac = normal_mac(rule.get("adapter")), normal_mac(rule.get("mac"))
            if isinstance(rule, dict) and adapter and mac and key == rule_key(adapter, mac):
                rules[key] = rule
        return {
            "rules": dict(list(rules.items())[:MAX_RULES]),
            "last": dict(data.get("last") or {}),
            "suggest": dict(data.get("suggest") or {}),
            "dryRun": bool(data.get("dryRun")),
        }

    def _save(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        temp = f"{self.path}.{secrets.token_hex(4)}.tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
        os.replace(temp, self.path)

    def state(self) -> dict[str, Any]:
        return self._load()

    def enabled(self, adapter: str | None, mac: str | None) -> dict[str, Any] | None:
        """The rule for exactly this adapter and device, or None. The one gate every action passes."""
        a, m = normal_mac(adapter), normal_mac(mac)
        if a is None or m is None:
            return None
        rule = self._load()["rules"].get(rule_key(a, m))
        return dict(rule) if rule else None

    def keys(self) -> set[str]:
        return set(self._load()["rules"])

    def dry_run(self) -> bool:
        return bool(self._load()["dryRun"])

    def set_dry_run(self, on: bool) -> None:
        data = self._load()
        data["dryRun"] = bool(on)
        self._save(data)
        self.action("dry-run", None, None, on=bool(on))

    def enable(self, adapter: Any, mac: Any, label: str = "") -> dict[str, Any]:
        a, m = normal_mac(adapter), normal_mac(mac)
        if a is None or m is None:
            raise ValueError("that is not a Bluetooth address")
        data = self._load()
        key = rule_key(a, m)
        if key in data["rules"]:
            return dict(data["rules"][key])
        if len(data["rules"]) >= MAX_RULES:
            raise ValueError(f"help can be on for at most {MAX_RULES} devices")
        rule = {
            "adapter": a,
            "mac": m,
            "label": (str(label).strip() or "Controller")[:40],
            "commit": True,
            "fullMode": False,
            "added": int(self.clock()),
        }
        data["rules"][key] = rule
        data["suggest"].pop(key, None)
        self._save(data)
        self.action("help-on", a, m)
        return dict(rule)

    def disable(self, adapter: Any, mac: Any) -> bool:
        a, m = normal_mac(adapter), normal_mac(mac)
        data = self._load()
        key = rule_key(a or "", m or "")
        if key not in data["rules"]:
            return False
        del data["rules"][key]
        data["last"].pop(key, None)
        self._save(data)
        self.action("help-off", a, m)
        return True

    def set_option(self, adapter: Any, mac: Any, option: str, on: bool) -> dict[str, Any]:
        if option not in ("commit", "fullMode"):
            raise ValueError("unknown option")
        a, m = normal_mac(adapter), normal_mac(mac)
        data = self._load()
        rule = data["rules"].get(rule_key(a or "", m or ""))
        if rule is None:
            raise ValueError("help is not on for that device")
        rule[option] = bool(on)
        self._save(data)
        self.action(f"option-{option}", a, m, on=bool(on))
        return dict(rule)

    def record(self, adapter: str, mac: str, diagnosis: dict[str, Any]) -> None:
        data = self._load()
        data["last"][rule_key(adapter, mac)] = diagnosis
        data["suggest"].pop(rule_key(adapter, mac), None)
        self._save(data)

    def suggest(self, adapter: str, mac: str, reason: str) -> bool:
        """Note that a device may need help (passive detection). Returns whether it is new."""
        data = self._load()
        key = rule_key(adapter, mac)
        if key in data["suggest"]:
            return False
        data["suggest"][key] = {"reason": reason, "at": int(self.clock())}
        self._save(data)
        return True

    def dismiss(self, adapter: Any, mac: Any) -> None:
        data = self._load()
        data["suggest"].pop(rule_key(normal_mac(adapter) or "", normal_mac(mac) or ""), None)
        self._save(data)

    def action(self, what: str, adapter: str | None, mac: str | None, **details: Any) -> None:
        """Append one line to the action log: when, what, which device (masked), dry run or not."""
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())),
            "action": what,
            "adapter": masked(adapter) if adapter else None,
            "device": masked(mac) if mac else None,
            **details,
        }
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def actions(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            with open(self.log_path, encoding="utf-8") as handle:
                lines = handle.readlines()[-limit:]
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out


# The journal (journalctl, System Binary Register, ADR-0082): bluetoothd and the kernel, for a
# short window only, always with a timeout. The deck user reads it through the wheel group.

Runner = Callable[[list[str]], str]


def default_runner(argv: list[str]) -> str:
    if shutil.which(argv[0]) is None:
        raise ReconnectError(f"{argv[0]} is not installed")
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=JOURNAL_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReconnectError(f"{argv[0]} did not answer ({type(exc).__name__})") from exc
    return done.stdout


def read_journal(since: float, runner: Runner = default_runner) -> list[str]:
    """bluetoothd's and the kernel's lines since ``since`` (seconds since the epoch), newest last."""
    lines: list[str] = []
    for scope in (["-u", "bluetooth.service"], ["-k"]):
        argv = ["journalctl", "--no-pager", "-q", "-o", "short-unix", f"--since=@{int(since)}", *scope]
        text = runner([*argv, "-n", str(JOURNAL_LINES)])
        lines.extend(line for line in text.splitlines() if line.strip())
    return sorted(lines)[-JOURNAL_LINES:]


SIGNS = {
    "collision": re.compile(r"Operation already in progress \(114\)"),
    "auth-failure": re.compile(r"Authentication Failure|authentication failed|Key missing", re.IGNORECASE),
    "security-block": re.compile(r"security block", re.IGNORECASE),
    "sixaxis": re.compile(r"sixaxis", re.IGNORECASE),
    "registered": re.compile(r"Registered \w+ controller|input: .* as /devices/virtual/misc/uhid", re.IGNORECASE),
    "report-timeout": re.compile(r"hidp.*timeout|report.*timed out", re.IGNORECASE),
}


def journal_signs(lines: list[str], mac: str | None = None) -> set[str]:
    """The failure signs in the lines. With ``mac``, lines naming another address are skipped."""
    found = set()
    for line in lines:
        named = {m.upper() for m in _ANY_MAC.findall(line)}
        if mac and named and mac not in named:
            continue
        for sign, pattern in SIGNS.items():
            if pattern.search(line):
                found.add(sign)
    return found


def redact(lines: list[str], adapter: str | None) -> list[str]:
    """The lines with this handheld's adapter address replaced (the bundle's "redact" option)."""
    if not adapter:
        return list(lines)
    pattern = re.compile(re.escape(adapter), re.IGNORECASE)
    dashed = re.compile(re.escape(adapter.replace(":", "_")), re.IGNORECASE)
    return [dashed.sub("HOST_ADAPTER", pattern.sub("HOST-ADAPTER", line)) for line in lines]


# Diagnosis. Without root Keepsake sees the bond, the connect attempts BlueZ reports, the journal
# and, through a cable pairing provider, the controller's stored host. The HCI capture that tells
# O2 from O3 comes with the root helper (R23); until then they share "the handshake fails".

ADVICE = {
    "O1": (
        "The controller never calls this handheld",
        "Its pairing was probably never saved on the controller. Keep Pair and commit on, then "
        "forget the controller and pair it again from Steam's Bluetooth settings. Until then, put "
        "it in pairing mode and use Reconnect.",
    ),
    "O2": (
        "The controller calls, but the handshake fails",
        "The controller reaches this handheld and is turned away within seconds. Put it in pairing "
        "mode and use Reconnect. The lasting fixes (cable pairing and the security setting) need "
        "the root helper, which comes in the next release.",
    ),
    "O4": (
        "This handheld has no pairing for the controller",
        "Pair it from Steam's Bluetooth settings with Pair and commit on, then try again.",
    ),
    "O5": (
        "The handheld does not know the controller's services yet",
        "Put the controller in pairing mode and use Reconnect once: BlueZ then keeps its service "
        "record, and later reconnects can work with the normal button.",
    ),
    "O6": (
        "Two connections collide",
        "The controller and this handheld try to connect at the same moment. Stop any other tool "
        "that reconnects controllers, then try again.",
    ),
    "O7": (
        "The controller connects, then drops",
        "Reconnecting is not the problem: the link fails after it is made. Check the controller's "
        "battery and its distance from the handheld.",
    ),
    "STORED": (
        "The controller stores this handheld",
        "Its pairing was saved correctly. Unplug it, turn it off, then run the diagnosis and press "
        "its button when asked, to see what happens when it calls.",
    ),
    "OTHER-HOST": (
        "The controller stores a different host",
        "It will call another device, not this handheld. Pair it again from Steam's Bluetooth "
        "settings with Pair and commit on.",
    ),
    "OK": ("The controller reconnected", "Nothing to fix: it reconnected with its normal button."),
    "NONE": (
        "Nothing was seen",
        "Keepsake saw nothing in the time allowed. Make sure the controller was off for 10 seconds "
        "before you pressed its button, and try again.",
    ),
}

RECOMMEND = {"O1": "commit", "O2": "assist", "O4": "pair", "O5": "assist", "OTHER-HOST": "pair", "O6": "none"}


def classify(
    bond: dict[str, Any] | None,
    events: list[tuple[float, str, bool]],
    signs: set[str] | None = None,
    identity: dict[str, Any] | None = None,
    adapter: str | None = None,
    watched: bool = True,
) -> dict[str, Any]:
    """The likely outcome from what was seen, with plain advice and the module to try.

    ``bond`` is the BlueZ device's state, ``events`` the ``(seconds, property, value)`` changes seen
    while the user pressed the button, ``signs`` the journal's failure signs and ``identity`` a
    cable pairing provider's read (controller and stored host). Evidence is weighed in order: the
    controller's own record, the bond, the journal, then what happened.
    """
    signs = signs or set()
    evidence: list[str] = []
    if identity and adapter and identity.get("host") != adapter:
        outcome = "OTHER-HOST" if identity.get("host") else "O1"
        evidence.append("the controller stores a different host" if identity.get("host") else "it stores no host")
    elif bond is not None and not (bond.get("Paired") or bond.get("Bonded")):
        outcome = "O4"
        evidence.append("BlueZ has no pairing for it")
    elif not watched:
        outcome = "STORED" if identity else "NONE"
        evidence.append("the controller stores this handheld" if identity else "nothing to compare")
    elif "collision" in signs:
        outcome = "O6"
        evidence.append("the journal shows two connections colliding")
    else:
        connects = [t for t, name, value in events if name == "Connected" and value]
        drops = [t for t, name, value in events if name == "Connected" and not value]
        if connects:
            first = connects[0]
            drop = next((t for t in drops if t >= first), None)
            if drop is None:
                outcome = "OK"
                evidence.append("it connected and stayed connected")
            elif drop - first <= 5.0:
                # No service record cached (no UUIDs on the bond) points to the SDP browse fault (F4).
                outcome = "O5" if bond is not None and not bond.get("UUIDs") else "O2"
                evidence.append(f"it connected and dropped after {drop - first:.1f} s")
            else:
                outcome = "O7"
                evidence.append(f"it stayed connected for {drop - first:.0f} s, then dropped")
        else:
            outcome = "O1" if bond is not None else "NONE"
            evidence.append("no connection attempt reached the handheld")
    for sign in sorted(signs - {"collision"}):
        evidence.append(f"journal: {sign.replace('-', ' ')}")
    title, advice = ADVICE[outcome]
    return {
        "outcome": outcome,
        "title": title,
        "advice": advice,
        "recommend": RECOMMEND.get(outcome),
        "evidence": evidence,
        "sixaxis": "sixaxis" in signs,
        "at": int(time.time()),
    }
