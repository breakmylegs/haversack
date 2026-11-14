// Typed bindings to the Python backend (main.py). Keep UI logic thin: the
// backend owns behaviour, the frontend only displays and forwards.
import { callable } from "@decky/api";

export interface Settings {
  schemaVersion: number;
  deviceId: string;
  deviceName: string;
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
