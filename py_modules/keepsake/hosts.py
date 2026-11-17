"""Which host Keepsake runs under, and the platform's own folders (ADR-0038).

Three hosts share one core:

- ``decky``: the plugin on a Decky handheld (or a Linux PC with Decky).
- ``linux-desktop``: a Linux PC or laptop without Decky, running ``keepsake.host``.
- ``windows``: a Windows PC running ``keepsake.host``.

On Windows the save folders the Ludusavi manifest names (``<winAppData>`` and
so on) are the user's known folders, read with ``SHGetKnownFolderPath`` so a
Documents folder redirected to OneDrive is found where it really is. Stdlib
only (``ctypes``), loaded only on Windows.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Mapping

HOSTS = ("decky", "linux-desktop", "windows")

# KnownFolders.h: FOLDERID_RoamingAppData, LocalAppData, LocalAppDataLow, Documents, SavedGames,
# Public and ProgramData, one for each Windows logical root in resolve.WIN_ROOTS.
KNOWN_FOLDERS = {
    "winAppData": "3EB685DB-65F9-4CF6-A03A-E3EF65729F3D",
    "winLocalAppData": "F1B32785-6FBA-4FCF-9D55-7B8E7F157091",
    "winLocalAppDataLow": "A520A1A4-1780-4FF6-BD18-167343C5AF16",
    "winDocuments": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "winSavedGames": "4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4",
    "winPublic": "DFDF76A2-C82A-4D63-906A-5644AC457385",
    "winProgramData": "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97",
}


def host(env: Mapping[str, str] | None = None, platform: str | None = None) -> str:
    """The host this process runs under. Decky sets its own environment for plugin backends."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if env.get("DECKY_PLUGIN_DIR") or env.get("DECKY_PLUGIN_RUNTIME_DIR"):
        return "decky"
    return "windows" if platform == "win32" else "linux-desktop"


def known_folder(root: str) -> str | None:
    """The real folder for a Windows logical root, or None when Windows cannot say (or on other systems)."""
    guid = KNOWN_FOLDERS.get(root)
    if guid is None or sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("data", ctypes.c_ubyte * 16)]  # noqa: RUF012

    folder_id = GUID()
    ctypes.memmove(folder_id.data, uuid.UUID(guid).bytes_le, 16)
    # windll exists only on Windows; mypy on other systems does not know it.
    shell32 = ctypes.windll.shell32  # type: ignore[attr-defined, unused-ignore]
    ole32 = ctypes.windll.ole32  # type: ignore[attr-defined, unused-ignore]
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    path = ctypes.c_wchar_p()
    result = shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path))
    try:
        return path.value if result == 0 and path.value else None
    finally:
        ole32.CoTaskMemFree(path)


def windows_roots() -> dict[str, str | None]:
    """Every Windows logical root on this machine."""
    return {root: known_folder(root) for root in KNOWN_FOLDERS}
