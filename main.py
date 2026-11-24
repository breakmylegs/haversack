# Thin Decky entry point. All logic lives in py_modules/keepsake.
import asyncio
from typing import Any

import decky

from keepsake.app import KeepsakeApp
from keepsake.paths import PluginPaths
from keepsake.rename import Gate


class Plugin:
    app: KeepsakeApp

    async def _main(self) -> None:
        self.gate = Gate(PluginPaths.from_env().settings_dir)
        await self._start()

    async def _start(self) -> None:
        # Haversack starts nothing while the old Keepsake is installed, and copies its data first (ADR-0089).
        if hasattr(self, "app") or not await asyncio.to_thread(self.gate.ready):
            if self.gate.error:
                decky.logger.error("Moving Keepsake's data failed: %s", self.gate.error)
            return
        self.app = KeepsakeApp(PluginPaths.from_env(), emit=decky.emit)
        await self.app.start()

    async def rename_status(self) -> dict[str, Any]:
        return self.gate.status(hasattr(self, "app"))

    async def rename_finish(self) -> dict[str, Any]:
        """After the user removed the old plugin: copy its data and start."""
        await self._start()
        return self.gate.status(hasattr(self, "app"))

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

    async def remote_copies_report(self, entries: Any) -> dict[str, Any]:
        return await self.app.remote_copies_report(entries)

    async def manifest_status(self) -> dict[str, Any]:
        return await self.app.manifest_status()

    async def refresh_manifest(self, force: bool = False) -> dict[str, Any]:
        return await self.app.refresh_manifest(force)

    async def manifest_progress(self) -> dict[str, Any]:
        return await self.app.manifest_progress()

    async def update_game_config(self, key: str, changes: dict[str, Any]) -> dict[str, Any]:
        return await self.app.update_game_config(key, changes)

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

    async def replication_status(self) -> dict[str, Any]:
        return await self.app.replication_status()

    async def replication_set_listener(self, on: bool) -> dict[str, Any]:
        return await self.app.replication_set_listener(on)

    async def replication_set_address(self, address: str) -> dict[str, Any]:
        return await self.app.replication_set_address(address)

    async def replication_pair(self, address: str) -> dict[str, Any]:
        return await self.app.replication_pair(address)

    async def replication_answer(self, pairing_id: str, ok: bool) -> dict[str, Any]:
        return await self.app.replication_answer(pairing_id, ok)

    async def replication_enter_code(self, pairing_id: str, code: str) -> dict[str, Any]:
        return await self.app.replication_enter_code(pairing_id, code)

    async def replication_cancel(self, pairing_id: str) -> dict[str, Any]:
        return await self.app.replication_cancel(pairing_id)

    async def replication_find(self) -> list[dict[str, Any]]:
        return await self.app.replication_find()

    async def replication_check(self, peer_id: str) -> dict[str, Any]:
        return await self.app.replication_check(peer_id)

    async def replication_remove(self, peer_id: str) -> dict[str, Any]:
        return await self.app.replication_remove(peer_id)

    async def replication_wake(self, peer_id: str) -> dict[str, Any]:
        return await self.app.replication_wake(peer_id)

    async def replication_transfers(self) -> dict[str, Any]:
        return await self.app.replication_transfers()

    async def replication_pause(self, job_id: str) -> dict[str, Any]:
        return await self.app.replication_pause(job_id)

    async def replication_resume(self, job_id: str) -> dict[str, Any]:
        return await self.app.replication_resume(job_id)

    async def replication_stop(self, job_id: str) -> dict[str, Any]:
        return await self.app.replication_stop(job_id)

    async def replication_send(self, key: str, peer_id: str) -> dict[str, Any]:
        return await self.app.replication_send(key, peer_id)

    async def replication_offers(self) -> dict[str, Any]:
        return await self.app.replication_offers()

    async def replication_offer_check(self, offer_id: str, copy_tool: bool = False) -> dict[str, Any]:
        return await self.app.replication_offer_check(offer_id, copy_tool)

    async def replication_accept(self, offer_id: str, copy_tool: bool = False) -> dict[str, Any]:
        return await self.app.replication_accept(offer_id, copy_tool)

    async def replication_decline(self, offer_id: str) -> dict[str, Any]:
        return await self.app.replication_decline(offer_id)

    async def device_checks(self) -> dict[str, Any]:
        return await self.app.device_checks()

    async def device_check_run(self, check_id: str) -> dict[str, Any]:
        return await self.app.device_check_run(check_id)

    async def device_checks_run_all(self) -> dict[str, Any]:
        return await self.app.device_checks_run_all()

    async def device_checks_export(self) -> dict[str, Any]:
        return await self.app.device_checks_export()

    async def replication_games(self) -> list[dict[str, Any]]:
        return await self.app.replication_games()

    async def replication_set_policy(self, link_id: str, policy: str) -> list[dict[str, Any]]:
        return await self.app.replication_set_policy(link_id, policy)

    async def replication_check_game(self, link_id: str) -> dict[str, Any]:
        return await self.app.replication_check_game(link_id)

    async def replication_send_update(self, link_id: str) -> list[dict[str, Any]]:
        return await self.app.replication_send_update(link_id)

    async def replication_apply_update(self, offer_id: str, take_theirs: bool = False) -> dict[str, Any]:
        return await self.app.replication_apply_update(offer_id, take_theirs)

    async def replication_keep_mine(self, offer_id: str) -> dict[str, Any]:
        return await self.app.replication_keep_mine(offer_id)

    async def replication_dismiss(self, offer_id: str) -> dict[str, Any]:
        return await self.app.replication_dismiss(offer_id)

    async def replication_withdraw(self, offer_id: str) -> dict[str, Any]:
        return await self.app.replication_withdraw(offer_id)

    async def replication_remove_game(self, offer_id: str) -> dict[str, Any]:
        return await self.app.replication_remove_game(offer_id)

    async def qam_shortcuts(self) -> dict[str, Any]:
        return await self.app.qam_shortcuts()

    async def run_shortcut(self, shortcut_id: str) -> dict[str, Any]:
        return await self.app.run_shortcut(shortcut_id)

    async def installer_stream_tiles(self) -> list[dict[str, Any]]:
        return await self.app.installer_stream_tiles()

    async def installer_stream_art_search(self, title: str) -> list[dict[str, Any]]:
        return await self.app.installer_stream_art_search(title)

    async def installer_stream_art_apply(self, appid: int, game_id: int) -> dict[str, Any]:
        return await self.app.installer_stream_art_apply(appid, game_id)

    async def emulator_setup(self) -> dict[str, Any]:
        return await self.app.emulator_setup()

    async def emulator_peer(self, peer_id: str) -> dict[str, Any]:
        return await self.app.emulator_peer(peer_id)

    async def emulator_send(self, peer_id: str, system: str, unit: str, with_keys: bool = False) -> dict[str, Any]:
        return await self.app.emulator_send(peer_id, system, unit, with_keys)

    async def save_navigation_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return await self.app.save_navigation_record(record)

    async def game_art_status(self, key: str) -> dict[str, Any]:
        return await self.app.game_art_status(key)

    async def game_art_apply(self, key: str, game_id: int) -> dict[str, Any]:
        return await self.app.game_art_apply(key, game_id)

    async def replication_activity(self) -> list[dict[str, Any]]:
        return await self.app.replication_activity()

    async def replication_stop_game(self, entry_id: str) -> list[dict[str, Any]]:
        return await self.app.replication_stop_game(entry_id)

    async def replication_clear_game(self, entry_id: str) -> list[dict[str, Any]]:
        return await self.app.replication_clear_game(entry_id)

    async def replication_peer_games(self, peer_id: str) -> list[dict[str, Any]]:
        return await self.app.replication_peer_games(peer_id)

    async def replication_get_game(self, peer_id: str, game_id: str, title: str = "") -> list[dict[str, Any]]:
        return await self.app.replication_get_game(peer_id, game_id, title)

    async def installer_status(self) -> dict[str, Any]:
        return await self.app.installer_status()

    async def installer_start(self, source: str, title: str, queue: bool = False) -> dict[str, Any]:
        return await self.app.installer_start(source, title, queue)

    async def installer_swap_disc(self, job_id: int, disc: str) -> dict[str, Any]:
        return await self.app.installer_swap_disc(job_id, disc)

    async def installer_net_locations(self) -> list[dict[str, Any]]:
        return await self.app.installer_net_locations()

    async def installer_net_remember(self, values: dict[str, Any]) -> list[dict[str, Any]]:
        return await self.app.installer_net_remember(values)

    async def installer_net_forget(self, location_id: str) -> list[dict[str, Any]]:
        return await self.app.installer_net_forget(location_id)

    async def installer_net_browse(self, access: dict[str, Any], url: str = "") -> dict[str, Any]:
        return await self.app.installer_net_browse(access, url)

    async def installer_net_find_smb(self) -> dict[str, Any]:
        return await self.app.installer_net_find_smb()

    async def installer_net_download(
        self, access: dict[str, Any], url: str, title: str, sha256: str = ""
    ) -> dict[str, Any]:
        return await self.app.installer_net_download(access, url, title, sha256)

    async def installer_net_cancel(self) -> dict[str, Any]:
        return await self.app.installer_net_cancel()

    async def installer_net_status(self) -> dict[str, Any]:
        return await self.app.installer_net_status()

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

    async def set_game_key(self, key: str, game_key: str | None, title: str | None = None) -> dict[str, Any]:
        return await self.app.set_game_key(key, game_key, title)

    async def on_game_event(self, kind: str, raw_id: Any) -> dict[str, Any]:
        return await self.app.on_game_event(kind, raw_id)

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

    async def export_diagnostics(self, frontend: dict[str, Any]) -> str:
        return await self.app.export_diagnostics(frontend)
