// Typed bindings to the Python backend (main.py). Keep UI logic thin: the
// backend owns behaviour, the frontend only displays and forwards.
import { callable } from "@decky/api";

export type UpdateChannel = "stable" | "prerelease";

export interface Settings {
  schemaVersion: number;
  deviceId: string;
  deviceName: string;
  updateChannel: UpdateChannel;
  gateMaxRemovedPercent: number;
  gateMaxSizeDropPercent: number;
  onedriveClientId: string;
  snapshotStore: "local" | "onedrive";
  launchPullTimeout: number;
  toastOnSync: boolean;
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

export interface ManifestStatus {
  available: boolean;
  fetched?: number;
  games?: number;
  entries?: number;
  skipped?: number;
  parseSeconds?: number;
  peakRssMb?: number | null;
  stale?: boolean;
  attribution: string;
}

export interface MatchInfo {
  method: "manual" | "steam-id" | "title" | "ambiguous" | "none" | "no-save-data" | "no-manifest";
  title: string | null;
  gameKey: string | null;
  candidates: string[];
}

export interface GameMatch extends MatchInfo {
  key: string;
  name: string;
  kind: "steam" | "shortcut";
}

export interface CustomPath {
  root: string;
  rel: string;
}

export interface GameConfig {
  matchTitle: string | null;
  aliases: string[];
  includeConfig: boolean;
  customPaths: CustomPath[];
  exclusions: string[];
  enabled: boolean;
  launchGate: "freeze" | "strict" | "off";
}

export interface PreviewEntry {
  source: "manifest" | "custom";
  path: string;
  root: string;
  pattern: string;
  tags: string;
  files: number;
  bytes: number;
  samples: string[];
}

export interface Preview {
  title: string | null;
  gameKey: string | null;
  platform: "proton" | "native";
  roots: Record<string, string | null>;
  entries: PreviewEntry[];
  skipped: { path: string; reason: string }[];
  escaped: string[];
  excluded: number;
  totalFiles: number;
  totalBytes: number;
  warnings: string[];
  match: MatchInfo;
}

export interface SnapshotSummary {
  snapId: string;
  created: string;
  kind: string;
  device: string | null;
  files: number;
  bytes: number;
  pinned?: boolean;
  pruned?: boolean;
  base?: boolean;
  reasons?: string[];
}

export interface SnapshotListing {
  gameKey?: string;
  snapshots: SnapshotSummary[];
  quarantine: SnapshotSummary[];
  prerestore: SnapshotSummary[];
}

export interface SnapshotResult {
  status: string;
  snapId?: string;
  reasons?: string[];
  prerestore?: string;
  created?: number;
  replaced?: number;
  deleted?: number;
}

export interface CloudStatus {
  clientIdSet: boolean;
  signedIn: boolean;
  signingIn: boolean;
  problem: string | null;
  store: "local" | "onedrive";
}

export interface SignInCode {
  userCode: string;
  verificationUri: string;
  expiresIn: number;
}

export const cloudStatus = callable<[], CloudStatus>("cloud_status");
export const startSignin = callable<[], SignInCode>("start_signin");
export const cancelSignin = callable<[], { ok: boolean }>("cancel_signin");
export const signOut = callable<[], { ok: boolean }>("sign_out");
export const testCloud = callable<[], { ok: boolean; folder?: string; error?: string }>("test_cloud");
export interface HeadSummary {
  snapId: string;
  device: string | null;
  created: string | null;
  files: number;
  bytes: number;
  kind: string | null;
}

export interface SyncConflict {
  kind: "adoption" | "fork" | "both-changed";
  heads: HeadSummary[];
  localFiles: number;
  raised: number;
}

export interface SyncStatus {
  available: boolean;
  reason?: string;
  gameKey?: string;
  base?: string | null;
  pending?: boolean;
  conflict?: SyncConflict | null;
  quarantined?: string;
  sessionOpen?: { started: number } | null;
  lastPush?: number;
  lastPull?: number;
}

export const onGameEvent = callable<[kind: "start" | "exit", rawId: number | string], { handled: number }>(
  "on_game_event",
);
export const strictWrap = callable<[key: string, currentOptions: string], { appid: number; options: string }>(
  "strict_wrap",
);
export const strictUnwrap = callable<[key: string, mode: string], { appid: number; options: string }>("strict_unwrap");
export const syncPull = callable<[key: string], Record<string, unknown>>("sync_pull");
export const syncPush = callable<[key: string], Record<string, unknown>>("sync_push");
export const resolveConflict = callable<[key: string, choice: string, head: string | null], Record<string, unknown>>(
  "resolve_conflict",
);
export const syncStatus = callable<[key: string], SyncStatus>("sync_status");
export const snapshotGame = callable<[key: string], SnapshotResult>("snapshot_game");
export const listSnapshots = callable<[key: string], SnapshotListing>("list_snapshots");
export const restoreSnapshot = callable<[key: string, snapId: string], SnapshotResult>("restore_snapshot");
export const undoRestore = callable<[key: string, prerestoreId: string], SnapshotResult>("undo_restore");
export const pinSnapshot = callable<[key: string, snapId: string], { ok: boolean }>("pin_snapshot");
export const releaseQuarantine = callable<[key: string, snapId: string, confirmed: boolean], SnapshotResult>(
  "release_quarantine",
);
export const runRetention = callable<[key: string], { pruned: string[]; kept: number; orphansDeleted: string[] }>(
  "run_retention",
);
export const manifestStatus = callable<[], ManifestStatus>("manifest_status");
export const refreshManifest = callable<[force: boolean], { ok: boolean; reason?: string; games?: number }>(
  "refresh_manifest",
);
export const matchGames = callable<[], GameMatch[]>("match_games");
export const searchTitles = callable<[query: string], string[]>("search_titles");
export const getGame = callable<[key: string], { game: GameEntry; config: GameConfig; match: MatchInfo }>("get_game");
export const updateGameConfig = callable<[key: string, changes: Partial<GameConfig>], GameConfig>(
  "update_game_config",
);
export const addCustomPath = callable<[key: string, absolutePath: string], GameConfig>("add_custom_path");
export const previewGame = callable<[key: string], Preview>("preview_game");
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
