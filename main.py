# Thin Decky entry point. All logic lives in py_modules/keepsake.
from typing import Any

import decky

from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths


class Plugin:
    app: KeepsakeApp

    async def _main(self) -> None:
        self.app = KeepsakeApp(PluginPaths.from_env(), emit=decky.emit)
        await self.app.start()

    async def _unload(self) -> None:
        if hasattr(self, "app"):
            await self.app.stop()

    async def _uninstall(self) -> None:
        # Decky calls this on every update as well as on uninstall (it uninstalls
        # the old version first). It must never delete settings, tokens or state.
        pass

    async def get_status(self) -> dict[str, Any]:
        return await self.app.get_status()

    async def take_startup_notice(self) -> dict[str, Any] | None:
        return await self.app.take_startup_notice()

    async def check_for_updates(self, force: bool = False) -> dict[str, Any]:
        return await self.app.check_for_updates(force)

    async def prepare_update(self, tag: str) -> dict[str, Any]:
        return await self.app.prepare_update(tag)

    async def discover_games(self, refresh: bool = False) -> dict[str, Any]:
        return await self.app.discover_games(refresh)

    async def check_running_prefix(self, key: str) -> dict[str, Any]:
        return await self.app.check_running_prefix(key)

    async def manifest_status(self) -> dict[str, Any]:
        return await self.app.manifest_status()

    async def refresh_manifest(self, force: bool = False) -> dict[str, Any]:
        return await self.app.refresh_manifest(force)

    async def match_games(self) -> list[dict[str, Any]]:
        return await self.app.match_games()

    async def search_titles(self, query: str) -> list[str]:
        return await self.app.search_titles(query)

    async def get_game(self, key: str) -> dict[str, Any]:
        return await self.app.get_game(key)

    async def update_game_config(self, key: str, changes: dict[str, Any]) -> dict[str, Any]:
        return await self.app.update_game_config(key, changes)

    async def add_custom_path(self, key: str, absolute_path: str) -> dict[str, Any]:
        return await self.app.add_custom_path(key, absolute_path)

    async def preview_game(self, key: str) -> dict[str, Any]:
        return await self.app.preview_game(key)

    async def cloud_status(self) -> dict[str, Any]:
        return await self.app.cloud_status()

    async def start_signin(self) -> dict[str, Any]:
        return await self.app.start_signin()

    async def cancel_signin(self) -> dict[str, Any]:
        return await self.app.cancel_signin()

    async def sign_out(self) -> dict[str, Any]:
        return await self.app.sign_out()

    async def test_cloud(self) -> dict[str, Any]:
        return await self.app.test_cloud()

    async def on_game_event(self, kind: str, raw_id: Any) -> dict[str, Any]:
        return await self.app.on_game_event(kind, raw_id)

    async def strict_wrap(self, key: str, current_options: str) -> dict[str, Any]:
        return await self.app.strict_wrap(key, current_options)

    async def strict_unwrap(self, key: str, mode: str = "freeze") -> dict[str, Any]:
        return await self.app.strict_unwrap(key, mode)

    async def sync_pull(self, key: str) -> dict[str, Any]:
        return await self.app.sync_pull(key)

    async def sync_push(self, key: str) -> dict[str, Any]:
        return await self.app.sync_push(key)

    async def resolve_conflict(self, key: str, choice: str, head: str | None = None) -> dict[str, Any]:
        return await self.app.resolve_conflict(key, choice, head)

    async def sync_status(self, key: str) -> dict[str, Any]:
        return await self.app.sync_status(key)

    async def idle_pass(self) -> list[dict[str, Any]]:
        return await self.app.idle_pass()

    async def snapshot_game(self, key: str) -> dict[str, Any]:
        return await self.app.snapshot_game(key)

    async def list_snapshots(self, key: str) -> dict[str, Any]:
        return await self.app.list_snapshots(key)

    async def restore_snapshot(self, key: str, snap_id: str) -> dict[str, Any]:
        return await self.app.restore_snapshot(key, snap_id)

    async def undo_restore(self, key: str, prerestore_id: str) -> dict[str, Any]:
        return await self.app.undo_restore(key, prerestore_id)

    async def pin_snapshot(self, key: str, snap_id: str) -> dict[str, Any]:
        return await self.app.pin_snapshot(key, snap_id)

    async def release_quarantine(self, key: str, snap_id: str, confirmed: bool) -> dict[str, Any]:
        return await self.app.release_quarantine(key, snap_id, confirmed)

    async def run_retention(self, key: str) -> dict[str, Any]:
        return await self.app.run_retention(key)

    async def simulate_sync_job(self, seconds: int = 30) -> dict[str, Any]:
        return await self.app.simulate_sync_job(seconds)

    async def get_settings(self) -> dict[str, Any]:
        return await self.app.get_settings()

    async def set_setting(self, key: str, value: Any) -> dict[str, Any]:
        return await self.app.set_setting(key, value)

    async def get_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        return await self.app.get_logs(limit)

    async def get_environment(self) -> dict[str, Any]:
        return await self.app.get_environment()

    async def get_steam_probe(self) -> dict[str, Any]:
        return await self.app.get_steam_probe()

    async def get_game_processes(self, appid: int) -> list[dict[str, Any]]:
        return await self.app.get_game_processes(appid)

    async def https_test(self) -> dict[str, Any]:
        return await self.app.https_test()

    async def record_probe_event(self, kind: str, payload: Any) -> int:
        return await self.app.record_probe_event(kind, payload)

    async def export_diagnostics(self, frontend: dict[str, Any]) -> str:
        return await self.app.export_diagnostics(frontend)

    async def freeze_test(self, appid: int, seconds: int = 5) -> dict[str, Any]:
        return await self.app.freeze_test(appid, seconds)
