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

    async def manifest_progress(self) -> dict[str, Any]:
        return await self.app.manifest_progress()

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

    async def start_signin(self, backend: str = "onedrive") -> dict[str, Any]:
        return await self.app.start_signin(backend)

    async def cancel_signin(self) -> dict[str, Any]:
        return await self.app.cancel_signin()

    async def sign_out(self, backend: str = "onedrive") -> dict[str, Any]:
        return await self.app.sign_out(backend)

    async def test_cloud(self, backend: str | None = None) -> dict[str, Any]:
        return await self.app.test_cloud(backend)

    async def backend_config(self, backend: str) -> dict[str, Any]:
        return await self.app.backend_config(backend)

    async def set_backend_config(self, backend: str, values: dict[str, Any]) -> dict[str, Any]:
        return await self.app.set_backend_config(backend, values)

    async def modules_status(self) -> dict[str, Any]:
        return await self.app.modules_status()

    async def set_module_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        return await self.app.set_module_enabled(name, enabled)

    async def reset_module(self, name: str) -> dict[str, Any]:
        return await self.app.reset_module(name)

    async def steam_probe(self) -> dict[str, Any]:
        return await self.app.steam_probe()

    async def steam_ops_claim(self) -> dict[str, Any] | None:
        return await self.app.steam_ops_claim()

    async def steam_ops_finish(self, op_id: int, ok: bool, result: dict[str, Any]) -> dict[str, Any]:
        return await self.app.steam_ops_finish(op_id, ok, result)

    async def steam_ops_list(self) -> list[dict[str, Any]]:
        return await self.app.steam_ops_list()

    async def installer_status(self) -> dict[str, Any]:
        return await self.app.installer_status()

    async def installer_start(self, source: str, title: str) -> dict[str, Any]:
        return await self.app.installer_start(source, title)

    async def installer_create_shortcut(self, job_id: int, installer_rel: str) -> dict[str, Any]:
        return await self.app.installer_create_shortcut(job_id, installer_rel)

    async def installer_finished_installing(self, job_id: int) -> dict[str, Any]:
        return await self.app.installer_finished_installing(job_id)

    async def installer_retarget(self, job_id: int, exe: str) -> dict[str, Any]:
        return await self.app.installer_retarget(job_id, exe)

    async def installer_cancel(self, job_id: int) -> dict[str, Any]:
        return await self.app.installer_cancel(job_id)

    async def installer_add_cd_drive(self, job_id: int) -> dict[str, Any]:
        return await self.app.installer_add_cd_drive(job_id)

    async def installer_remove_shortcut(self, job_id: int) -> dict[str, Any]:
        return await self.app.installer_remove_shortcut(job_id)

    async def installer_artwork_search(self, job_id: int) -> list[dict[str, Any]]:
        return await self.app.installer_artwork_search(job_id)

    async def installer_artwork_apply(self, job_id: int, game_id: int) -> dict[str, Any]:
        return await self.app.installer_artwork_apply(job_id, game_id)

    async def installer_handoff(self, job_id: int) -> dict[str, Any]:
        return await self.app.installer_handoff(job_id)

    async def steam_ops_file(self, op_id: int) -> dict[str, Any]:
        return await self.app.steam_ops_file(op_id)

    async def enable_steam_without_cloud(self) -> dict[str, Any]:
        return await self.app.enable_steam_without_cloud()

    async def on_suspend(self) -> dict[str, Any]:
        return await self.app.on_suspend()

    async def ludusavi_scan(self, root: str) -> dict[str, Any]:
        return await self.app.ludusavi_scan(root)

    async def ludusavi_import(self, root: str, folder: str, backup_ids: list[str], game_key: str) -> dict[str, Any]:
        return await self.app.ludusavi_import(root, folder, backup_ids, game_key)

    async def set_game_key(self, key: str, game_key: str | None, title: str | None = None) -> dict[str, Any]:
        return await self.app.set_game_key(key, game_key, title)

    async def approve_match(self, key: str) -> dict[str, Any]:
        return await self.app.approve_match(key)

    async def reject_match(self, key: str) -> dict[str, Any]:
        return await self.app.reject_match(key)

    async def new_game_key(self, key: str) -> dict[str, Any]:
        return await self.app.new_game_key(key)

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

    async def qam_summary(self) -> dict[str, Any]:
        return await self.app.qam_summary()

    async def sync_now(self) -> dict[str, Any]:
        return await self.app.sync_now()

    async def list_conflicts(self) -> list[dict[str, Any]]:
        return await self.app.list_conflicts()

    async def conflict_details(self, key: str) -> dict[str, Any]:
        return await self.app.conflict_details(key)

    async def recent_history(self, limit: int = 50) -> dict[str, Any]:
        return await self.app.recent_history(limit)

    async def plan_sync(self, keys: list[str]) -> list[dict[str, Any]]:
        return await self.app.plan_sync(keys)

    async def finish_setup(self, keys: list[str]) -> dict[str, Any]:
        return await self.app.finish_setup(keys)

    async def health_checks(self, probe: bool = True) -> dict[str, Any]:
        return await self.app.health_checks(probe)

    async def game_config_sync(self, key: str) -> dict[str, Any]:
        return await self.app.game_config_sync(key)

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
