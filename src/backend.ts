// Typed bindings to the Python backend (main.py). Keep UI logic thin: the
// backend owns behaviour, the frontend only displays and forwards.
import { callable } from "@decky/api";

export type UpdateChannel = "stable" | "prerelease";

export interface Settings {
  schemaVersion: number;
  deviceId: string;
  deviceName: string;
  updateChannel: UpdateChannel;
  readOnly: boolean;
}

export interface Status {
  version: string;
  safeMode: boolean;
  busy: string | null;
}

export interface ReleaseInfo {
  tag: string;
  version: string;
  prerelease: boolean;
  published: string;
  notes: string;
  zip_name: string;
  zip_url: string | null;
  complete: boolean;
}

export interface UpdateStatus {
  current: string;
  channel: UpdateChannel;
  latest: ReleaseInfo | null;
  updateAvailable: boolean;
  notify: boolean;
  releases: ReleaseInfo[];
  lastCheck: number | null;
  error: string | null;
}

export type PreparedUpdate =
  | {
      ok: true;
      artifact: string;
      name: string;
      version: string;
      displayVersion: string;
      sha256: string;
      installType: number;
    }
  | { ok: false; reason: string; detail?: string };

export interface StartupNotice {
  from: string;
  to: string;
}

export interface LogRecord {
  ts: string;
  level: string;
  event: string;
  msg: string;
  fields?: Record<string, unknown>;
  exc?: string;
}

export interface FreezeTestResult {
  ok: boolean;
  reason?: string;
  stopped?: number;
  resumed?: number;
  seconds?: number;
}

export interface HttpsTestResult {
  ok: boolean;
  status?: number;
  ms?: number;
  error?: string;
}

export interface GameEntry {
  key: string;
  kind: "steam" | "shortcut";
  appid: number;
  name: string;
  user_id: string | null;
  is_default_user: boolean;
  prefix: string | null;
  prefix_library_index: number | null;
  base_dir: string | null;
  exe_inside_prefix: boolean;
  last_played: number;
  notes: string[];
}

export interface DiscoveryResult {
  roots: { path: string; libraries: string[]; users: number; defaultUser: string | null }[];
  games: GameEntry[];
  mismatches: Record<string, unknown>;
}

export interface CrossCheck {
  status: "match" | "mismatch" | "unknown";
  observed?: string[];
  reason?: string;
}

export const discoverGames = callable<[refresh: boolean], DiscoveryResult>("discover_games");
export const checkRunningPrefix = callable<[key: string], CrossCheck>("check_running_prefix");
export const getStatus = callable<[], Status>("get_status");
export const takeStartupNotice = callable<[], StartupNotice | null>("take_startup_notice");
export const checkForUpdates = callable<[force: boolean], UpdateStatus>("check_for_updates");
export const prepareUpdate = callable<[tag: string], PreparedUpdate>("prepare_update");
export const simulateSyncJob = callable<[seconds: number], { ok: boolean; seconds: number }>("simulate_sync_job");
export const getSettings = callable<[], Settings>("get_settings");
export const setSetting = callable<[key: string, value: unknown], Settings>("set_setting");
export const getLogs = callable<[limit: number], LogRecord[]>("get_logs");
export const getEnvironment = callable<[], Record<string, unknown>>("get_environment");
export const getSteamProbe = callable<[], Record<string, unknown>>("get_steam_probe");
export const getGameProcesses = callable<[appid: number], Record<string, unknown>[]>("get_game_processes");
export const httpsTest = callable<[], HttpsTestResult>("https_test");
export const recordProbeEvent = callable<[kind: string, payload: unknown], number>("record_probe_event");
export const exportDiagnostics = callable<[frontend: Record<string, unknown>], string>("export_diagnostics");
export const freezeTest = callable<[appid: number, seconds: number], FreezeTestResult>("freeze_test");
