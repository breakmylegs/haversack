"""CD drive emulation for installers that insist on a disc (v2 spec 8.3, slice 22, ADR-0027).

Wine maps drive letters through links in ``<pfx>/dosdevices``: ``d:`` to the
mounted disc's folder and ``d::`` to its block device. The drive type comes from
``HKLM\\Software\\Wine\\Drives`` in ``system.reg``, set to ``cdrom`` with the
slice 11 registry engine (backup, atomic write, read-back). Both are in the
write allowlist for the game being installed (v2 section 6.3). Only links this
module made are ever removed.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from .. import registry

LETTERS = "defghijklmnopqrstuvwxy"  # c: is the Windows drive and z: the Linux root
DRIVES_KEY = "Software\\Wine\\Drives"


class CdromError(ValueError):
    pass


def _dosdevices(prefix: str) -> str:
    return os.path.join(prefix, "pfx", "dosdevices")


def add_drive(
    prefix: str,
    mount: str,
    device: str,
    backup_dir: str,
    symlink: Callable[[str, str], None] = os.symlink,
) -> dict[str, Any]:
    """Make the mounted disc a CD drive in ``prefix``; returns the letter and the links made.

    Refuses until Proton has created the prefix (``system.reg`` present), so
    Proton's own first-run setup is never disturbed.
    """
    system_reg = os.path.join(prefix, "pfx", "system.reg")
    dosdevices = _dosdevices(prefix)
    if not os.path.isfile(system_reg) or not os.path.isdir(dosdevices):
        raise CdromError("start the installer shortcut once and quit it, so Proton creates its prefix first")
    for letter in LETTERS:
        link = os.path.join(dosdevices, f"{letter}:")
        if os.path.lexists(link):
            if os.path.islink(link) and os.readlink(link) == mount:
                return {"letter": letter, "links": [], "registry": "unchanged"}  # already this disc
            continue
        symlink(mount, link)
        links = [link]
        raw = os.path.join(dosdevices, f"{letter}::")
        if device and not os.path.lexists(raw):
            symlink(device, raw)
            links.append(raw)
        try:
            written = registry.set_values(system_reg, DRIVES_KEY, {f"{letter}:": '"cdrom"'}, backup_dir)
        except (registry.RegistryError, OSError):
            remove_links(links, {link: mount, raw: device})
            raise
        return {"letter": letter, "links": links, "registry": written.get("status", "written")}
    raise CdromError("every drive letter from D: to Y: is already in use in this prefix")


def remove_links(links: list[str], targets: dict[str, str]) -> list[str]:
    """Remove links this module made, only while they still point where it set them."""
    removed = []
    for link in links:
        if os.path.islink(link) and os.readlink(link) == targets.get(link):
            os.unlink(link)
            removed.append(link)
    return removed


def repoint(
    links: list[str],
    targets: dict[str, str],
    new_target_for: Callable[[str], str],
    symlink: Callable[[str, str], None] = os.symlink,
) -> dict[str, str]:
    """Point each of Keepsake's drive links at a new disc, one rename each (ADR-0053).

    Every link is checked first, so a link changed outside Keepsake stops the swap before anything moves.
    Returns the new targets.
    """
    for link in links:
        if not os.path.islink(link) or os.readlink(link) != targets.get(link):
            raise CdromError("the disc drive was changed outside Haversack; swap the disc by hand")
    new: dict[str, str] = {}
    for link in links:
        target = new_target_for(link)
        temporary = link + ".keepsake-swap"
        if os.path.lexists(temporary):
            os.unlink(temporary)
        symlink(target, temporary)
        os.replace(temporary, link)
        new[link] = target
    return new
