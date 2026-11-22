"""Fan control on the Legion Go 2 through its embedded controller, and the Go 1's full fan speed (ADR-0085).

**Go 2 (83N0; 83N1 as a beta).** The EC takes an RPM override at 0xC6C8/9 (16-bit little endian):
0 hands the fan back to the firmware, 1500 to 4800 sets a speed. The measured speed is at
0xC6C0/1, the EC version at 0xC300/1, the power mode at 0xC683. The EC is reached through
``/dev/port``, index port 0x4E and data port 0x4F: three selector rounds (0x11 high address byte,
0x10 low byte, 0x12 data), each selector write read back, under ``flock``. Only the addresses in
``READS`` are read and only the override is written.

Overrides are only for the validated firmware (BIOS RRCN16WW with EC 1.16) or a pair that passed
the self-test on this device, and only under a lease: when Keepsake stops renewing it, the fan is
handed back to the firmware. At 101 °C or above the helper sets the ceiling itself.

**Go 1 (83E1).** Full fan speed through the firmware attribute ``fan_full_speed`` (kernel 7.2 and
later), under the same lease. Its custom fan table needs ``acpi_call``, which is not used (P9).
"""

from __future__ import annotations

import glob
import os
import time
from collections.abc import Callable
from typing import Any

INDEX, DATA = 0x4E, 0x4F
RPM, FACTORY, OVERRIDE, MODE, EC_VERSION = 0xC6C0, 0xC6C2, 0xC6C8, 0xC683, 0xC300
GO1_RPM = 0xC664
READS = {0xC300, 0xC301, 0xC683, 0xC6C0, 0xC6C1, 0xC6C2, 0xC6C3, 0xC6C8, 0xC6C9, 0xC664, 0xC665}
WRITES = {0xC6C8, 0xC6C9}
MIN_RPM, MAX_RPM, CEILING = 1500, 4800, 5200
FAILSAFE_C = 101.0
MAX_LEASE = 60.0
VALIDATED = {("RRCN16WW", "1.16")}
MODES = {176: "performance", 177: "balanced", 178: "quiet", 179: "custom"}
CONFLICT_MODULES = ("legion_laptop", "gpd_fan")


class FanError(Exception):
    pass


def _text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(128).strip()
    except OSError:
        return ""


def model(dmi: str = "/sys/class/dmi/id") -> str | None:
    """ "go2", "go2-beta", "go1" or None, from exact DMI strings (never guessed)."""
    vendor, product = _text(os.path.join(dmi, "sys_vendor")), _text(os.path.join(dmi, "product_name"))
    version, board = _text(os.path.join(dmi, "product_version")), _text(os.path.join(dmi, "board_name"))
    if vendor != "LENOVO":
        return None
    if product == "83N0" and version == "Legion Go 8ASP2" and board == "LNVNB161216":
        return "go2"
    bios = _text(os.path.join(dmi, "bios_version"))
    if product == "83N1" and version == "Legion Go 8AHP2" and bios.startswith("RQCN"):
        return "go2-beta"
    if product == "83E1":
        return "go1"
    return None


def conflicts(proc: str = "/proc") -> list[str]:
    """Other fan drivers, or anything else claiming the EC's index ports."""
    found = []
    modules = ""
    try:
        with open(os.path.join(proc, "modules"), encoding="utf-8", errors="replace") as handle:
            modules = handle.read(1 << 20)
    except OSError:
        pass
    for name in CONFLICT_MODULES:
        if any(line.split(" ", 1)[0] == name for line in modules.splitlines()):
            found.append(f"the {name} driver")
    try:
        with open(os.path.join(proc, "ioports"), encoding="utf-8", errors="replace") as handle:
            for line in handle:
                span, _, owner = line.strip().partition(" : ")
                low, _, high = span.partition("-")
                if low and high and int(low, 16) <= DATA and int(high, 16) >= INDEX:
                    found.append(f"{owner.strip() or 'a driver'} on the EC ports")
    except (OSError, ValueError):
        pass
    return found


class Port:
    """``/dev/port`` byte access: tests replace it with a fake EC."""

    def __init__(self, path: str = "/dev/port") -> None:
        self.fd = os.open(path, os.O_RDWR)
        import fcntl  # ADR-0030: only here

        fcntl.flock(self.fd, fcntl.LOCK_EX)  # type: ignore[attr-defined, unused-ignore]

    def out(self, port: int, value: int) -> None:
        os.pwrite(self.fd, bytes([value]), port)  # type: ignore[attr-defined, unused-ignore]

    def inb(self, port: int) -> int:
        data: bytes = os.pread(self.fd, 1, port)  # type: ignore[attr-defined, unused-ignore]
        return data[0]

    def close(self) -> None:
        os.close(self.fd)


class EC:
    def __init__(self, port: Any) -> None:
        self.port = port

    def _select(self, selector: int, value: int) -> None:
        self.port.out(INDEX, 0x2E)
        self.port.out(DATA, selector)
        self.port.out(INDEX, 0x2F)
        self.port.out(DATA, value)
        self.port.out(INDEX, 0x2F)
        if self.port.inb(DATA) != value:
            raise FanError("the embedded controller did not take the address")

    def _address(self, address: int) -> None:
        self._select(0x11, address >> 8)
        self._select(0x10, address & 0xFF)
        self.port.out(INDEX, 0x2E)
        self.port.out(DATA, 0x12)
        self.port.out(INDEX, 0x2F)

    def read(self, address: int) -> int:
        if address not in READS:
            raise FanError("that EC address is not allowed")
        self._address(address)
        return int(self.port.inb(DATA))

    def write(self, address: int, value: int) -> None:
        if address not in WRITES:
            raise FanError("that EC address may not be written")
        self._address(address)
        self.port.out(DATA, value & 0xFF)

    def word(self, address: int) -> int:
        return self.read(address) | (self.read(address + 1) << 8)

    def set_override(self, rpm: int) -> int:
        """Write the override and read it back. 0 hands the fan back to the firmware."""
        if rpm != 0 and not MIN_RPM <= rpm <= CEILING:
            raise FanError(f"a fan speed is {MIN_RPM} to {CEILING} RPM")
        low, high = rpm & 0xFF, rpm >> 8
        current = self.word(OVERRIDE)
        # Write the byte whose change keeps the intermediate value nearest the target first.
        first_high = abs(((high << 8) | (current & 0xFF)) - rpm) <= abs(((current & 0xFF00) | low) - rpm)
        writes = [(OVERRIDE + 1, high), (OVERRIDE, low)]
        for address, value in writes if first_high else writes[::-1]:
            self.write(address, value)
        after = self.word(OVERRIDE)
        if after != rpm:
            raise FanError("the embedded controller did not keep the fan speed")
        return after


def temperature(hwmon: str = "/sys/class/hwmon") -> float | None:
    """The hotter of the CPU (k10temp) and GPU (amdgpu) sensors, °C."""
    best = None
    for folder in glob.glob(os.path.join(hwmon, "hwmon*")):
        if _text(os.path.join(folder, "name")) in ("k10temp", "amdgpu"):
            raw = _text(os.path.join(folder, "temp1_input"))
            if raw.lstrip("-").isdigit():
                value = int(raw) / 1000
                best = value if best is None else max(best, value)
    return best


def full_speed_path(root: str = "/sys/class/firmware-attributes") -> str | None:
    for path in sorted(
        glob.glob(os.path.join(root, "lenovo-wmi-other-*", "attributes", "fan_full_speed", "current_value"))
    ):
        return path
    return None


class Fans:
    """The helper's fan state: one owner (Keepsake), one lease, hand-back on expiry."""

    def __init__(
        self,
        opener: Callable[[], Any] = Port,
        dmi: str = "/sys/class/dmi/id",
        proc: str = "/proc",
        hwmon: str = "/sys/class/hwmon",
        attrs: str = "/sys/class/firmware-attributes",
        passed: Callable[[], set[tuple[str, str]]] = set,
        record_pass: Callable[[tuple[str, str]], None] = lambda pair: None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.opener, self.dmi, self.proc, self.hwmon, self.attrs = opener, dmi, proc, hwmon, attrs
        self.passed, self.record_pass = passed, record_pass
        self.clock, self.sleep = clock, sleep
        self.lease_until = 0.0
        self.controlling = False  # Go 2 override or Go 1 full speed is Keepsake's

    def _ec(self, work: Callable[[EC], Any]) -> Any:
        port = self.opener()
        try:
            return work(EC(port))
        finally:
            port.close()

    def firmware(self) -> tuple[str, str] | None:
        bios = _text(os.path.join(self.dmi, "bios_version"))
        try:
            ec = self._ec(lambda e: f"{e.read(EC_VERSION)}.{e.read(EC_VERSION + 1):02d}")
        except (OSError, FanError):
            return None
        return bios, ec

    def validated(self) -> bool:
        pair = self.firmware()
        return pair is not None and (pair in VALIDATED or pair in self.passed())

    def status(self) -> dict[str, Any]:
        which = model(self.dmi)
        out: dict[str, Any] = {
            "model": which,
            "temperature": temperature(self.hwmon),
            "conflicts": conflicts(self.proc),
            "controlling": self.controlling,
            "acpiCall": os.path.exists(os.path.join(self.proc, "acpi", "call")),
            "fullSpeedAttribute": full_speed_path(self.attrs) is not None,
        }
        if which in ("go2", "go2-beta"):
            pair = self.firmware()
            out["firmware"] = {"bios": pair[0], "ec": pair[1]} if pair else None
            out["validated"] = bool(pair and (pair in VALIDATED or pair in self.passed()))
            try:
                out |= self._ec(
                    lambda e: {"rpm": e.word(RPM), "override": e.word(OVERRIDE), "mode": MODES.get(e.read(MODE))}
                )
            except (OSError, FanError) as exc:
                out["problem"] = str(exc)[:120]
        elif which == "go1":
            try:
                out["rpm"] = self._ec(lambda e: e.word(GO1_RPM))
            except (OSError, FanError):
                out["rpm"] = None
        return out

    def _guard(self) -> str:
        which = model(self.dmi)
        if which is None:
            raise FanError("fan control is only for the Legion Go and Legion Go 2")
        found = conflicts(self.proc)
        if found:
            raise FanError(f"another fan control is active: {', '.join(found)}")
        return which

    def set_rpm(self, rpm: int, lease: float) -> dict[str, Any]:
        if self._guard() not in ("go2", "go2-beta"):
            raise FanError("fan speeds can be set on the Legion Go 2 only")
        if not 0 < lease <= MAX_LEASE:
            raise FanError("a fan speed needs a lease of up to 60 seconds")
        if not self.validated():
            raise FanError("this BIOS and EC have not been checked: run the fan test first")
        temp = temperature(self.hwmon)
        if temp is not None and temp >= FAILSAFE_C:
            rpm = max(rpm, MAX_RPM)
        if not isinstance(rpm, int) or isinstance(rpm, bool) or not MIN_RPM <= rpm <= CEILING:
            raise FanError(f"a fan speed is {MIN_RPM} to {CEILING} RPM")
        after = self._ec(lambda e: e.set_override(rpm))
        self.controlling, self.lease_until = True, self.clock() + lease
        return {"override": after}

    def release(self) -> dict[str, Any]:
        """Hand the fan back to the firmware (Go 2 override 0, Go 1 full speed off)."""
        which = model(self.dmi)
        if which in ("go2", "go2-beta"):
            self._ec(lambda e: e.set_override(0))
        elif which == "go1":
            path = full_speed_path(self.attrs)
            if path:
                with open(path, "w", encoding="ascii") as handle:
                    handle.write("0")
        self.controlling, self.lease_until = False, 0.0
        return {"released": True}

    def full_speed(self, on: bool, lease: float) -> dict[str, Any]:
        if self._guard() != "go1":
            raise FanError("full fan speed through the firmware is for the Legion Go")
        path = full_speed_path(self.attrs)
        if path is None:
            raise FanError("this kernel does not offer full fan speed (it needs 7.2 or later)")
        if on and not 0 < lease <= MAX_LEASE:
            raise FanError("full fan speed needs a lease of up to 60 seconds")
        with open(path, "w", encoding="ascii") as handle:
            handle.write("1" if on else "0")
        if _text(path) != ("1" if on else "0"):
            raise FanError("the firmware did not keep full fan speed")
        self.controlling, self.lease_until = bool(on), (self.clock() + lease if on else 0.0)
        return {"fullSpeed": bool(on)}

    def renew(self, lease: float) -> None:
        if not 0 < lease <= MAX_LEASE:
            raise FanError("a lease is up to 60 seconds")
        if self.controlling:
            self.lease_until = self.clock() + lease

    def selftest(self) -> dict[str, Any]:
        """For a BIOS and EC pair not on the validated list: ask for a speed, check the fan gets there,
        hand back, and remember the pair if it passed. About 15 seconds."""
        if self._guard() not in ("go2", "go2-beta"):
            raise FanError("the fan test is for the Legion Go 2")
        pair = self.firmware()
        if pair is None:
            raise FanError("the embedded controller could not be read")
        start = self._ec(lambda e: e.word(RPM))
        wanted = 4800 if start >= 2200 else 3000
        hits = 0
        try:
            self._ec(lambda e: e.set_override(wanted))
            deadline = self.clock() + 15.0
            while self.clock() < deadline and hits < 2:
                self.sleep(1.0)
                rpm = self._ec(lambda e: e.word(RPM))
                hits = hits + 1 if abs(rpm - wanted) <= wanted * 0.15 else 0
        finally:
            self._ec(lambda e: e.set_override(0))
            self.controlling = False
        released = all(self._ec(lambda e: e.word(OVERRIDE)) == 0 for _ in range(3))
        ok = hits >= 2 and released
        if ok:
            self.record_pass(pair)
        return {"passed": ok, "firmware": {"bios": pair[0], "ec": pair[1]}, "target": wanted}

    def tick(self) -> str | None:
        """Every few seconds: an expired lease hands back; 101 °C or more sets the ceiling."""
        if not self.controlling:
            return None
        if self.clock() > self.lease_until:
            self.release()
            return "lease expired"
        temp = temperature(self.hwmon)
        if temp is not None and temp >= FAILSAFE_C and model(self.dmi) in ("go2", "go2-beta"):
            self._ec(lambda e: e.set_override(MAX_RPM))
            return "failsafe"
        return None
