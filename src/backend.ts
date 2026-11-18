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
  snapshotStore: Backend;
  launchPullTimeout: number;
  toastOnSync: boolean;
  idleSyncMinutes: number;
  showSteamApps: boolean;
  setupComplete: boolean;
  registrySync: boolean;
  steamCloudDetection: boolean;
  suspendSnapshots: boolean;
  libraryRoot: string;
  /** ADR-0044: how each provider signs in from Gaming Mode. */
  gamingModeSignin: Record<"onedrive" | "gdrive", SigninMethod>;
  readOnly: boolean;
}

export type SigninMethod = "browser" | "phone";

export type SteamCloud = "cloud" | "no-cloud" | "unknown" | null;

export interface SteamOp {
  id: number;
  module: string;
  kind: string;
  payload: Record<string, unknown>;
}

export interface ModuleStatus {
  name: string;
  title: string;
  description: string;
  writes: string;
  available: boolean;
  flag: boolean;
  running: boolean;
  failed: string | null;
  health: HealthCheck[];
}

export interface ModulesStatus {
  modules: ModuleStatus[];
  stateDatabase: boolean;
  locks: Record<string, string>;
  steamOpsPending: number;
}

export interface InstallJob {
  id: number;
  title: string;
  state: "choose-installer" | "creating-shortcut" | "run-installer" | "choose-game" | "retargeting" | "done" | "failed" | "cancelled";
  kind: "iso" | "folder";
  source: string;
  target: string;
  windowsTarget: string;
  installers: string[];
  candidates?: { path: string; size: number; score: number }[];
  appid?: number;
  error?: string;
  cdDrive?: { letter: string };
  shortcutRemoved?: boolean;
  gameExe?: string;
  artwork?: Record<string, boolean>;
}

export interface InstallerStatus {
  running: boolean;
  udisks: boolean;
  libraryRoot: string;
  artwork: boolean;
  artworkKey: boolean;
  sources: { home: string; network: string[]; removable: string[] };
  jobs: InstallJob[];
  /** Free bytes where network downloads are staged (ADR-0033). */
  stagingFree: number | null;
  download: NetDownload;
}

// Installing from a network location that is not mounted (ADR-0033). Passwords never come back.
export interface NetLocation {
  id: string;
  url: string;
  username: string;
  passwordSet: boolean;
}
export interface NetAccess {
  locationId?: string;
  url?: string;
  username?: string;
  password?: string;
  /** Other hosts the user allowed after a redirect, for this action only. */
  allowHosts?: string[];
}
export interface NetEntry {
  name: string;
  url: string;
  kind: "folder" | "iso";
}
export interface NetDownload {
  running: boolean;
  name?: string;
  title?: string;
  done?: number;
  total?: number | null;
  rate?: number;
  job?: number;
  cancelled?: boolean;
  error?: string;
  redirectHost?: string;
}
export const installerNetLocations = callable<[], NetLocation[]>("installer_net_locations");
export const installerNetRemember = callable<
  [values: { id?: string; url: string; username: string; password: string }],
  NetLocation[]
>("installer_net_remember");
export const installerNetForget = callable<[id: string], NetLocation[]>("installer_net_forget");
export const installerNetBrowse = callable<
  [access: NetAccess, url: string],
  { url: string; entries: NetEntry[]; redirectHost?: string; error?: string }
>("installer_net_browse");
export const installerNetDownload = callable<[access: NetAccess, url: string, title: string, sha256: string], NetDownload>(
  "installer_net_download",
);
export const installerNetCancel = callable<[], NetDownload>("installer_net_cancel");

export const installerStatus = callable<[], InstallerStatus>("installer_status");
export const installerAddCdDrive = callable<[jobId: number], InstallJob>("installer_add_cd_drive");
export const installerRemoveShortcut = callable<[jobId: number], InstallJob>("installer_remove_shortcut");
export const installerArtworkSearch = callable<[jobId: number], { id: number; name: string; verified: boolean }[]>(
  "installer_artwork_search",
);
export const installerArtworkApply = callable<[jobId: number, gameId: number], InstallJob>("installer_artwork_apply");
export const installerHandoff = callable<[jobId: number], { key: string; replication: boolean }>("installer_handoff");
export const steamOpsFile = callable<[id: number], { base64: string }>("steam_ops_file");
// The SteamGridDB key is kept with the backend secrets; only whether it is set comes back.
export const saveSteamGridDbKey = callable<[kind: "steamgriddb", values: { apiKey: string }], { configured: boolean }>(
  "set_backend_config",
);
export const installerStart = callable<[source: string, title: string], InstallJob>("installer_start");
export const installerCreateShortcut = callable<[jobId: number, installer: string], InstallJob>("installer_create_shortcut");
export const installerFinishedInstalling = callable<[jobId: number], InstallJob>("installer_finished_installing");
export const installerRetarget = callable<[jobId: number, exe: string], InstallJob>("installer_retarget");
export const installerCancel = callable<[jobId: number], InstallJob>("installer_cancel");

export const modulesStatus = callable<[], ModulesStatus>("modules_status");
export const setModuleEnabled = callable<[name: string, enabled: boolean], ModulesStatus>("set_module_enabled");
export const resetModule = callable<[name: string], ModulesStatus>("reset_module");
export const steamProbe = callable<[], { id: number }>("steam_probe");
export const steamOpsClaim = callable<[], SteamOp | null>("steam_ops_claim");
export const steamOpsFinish = callable<[id: number, ok: boolean, result: Record<string, unknown>], { ok: boolean }>(
  "steam_ops_finish",
);
export const steamOpsList = callable<[], (SteamOp & { state: string; result: Record<string, unknown> | null })[]>(
  "steam_ops_list",
);

export const onSuspend = callable<[], { started: number }>("on_suspend");
export const enableSteamWithoutCloud = callable<[], { enabled: string[] }>("enable_steam_without_cloud");

export type Backend = "local" | "onedrive" | "gdrive" | "webdav" | "s3";

export interface BackendConfig {
  configured: boolean;
  [field: string]: string | boolean;
}

export interface LudusaviBackup {
  id: string;
  kind: "full" | "differential";
  when: string | null;
  created: number | null;
  files: number;
}

export interface LudusaviGame {
  folder: string;
  name: string;
  backups: LudusaviBackup[];
  error: string | null;
  gameKey: string;
  inManifest: boolean;
  localGame: string | null;
}

export interface ImportResult {
  backup: string;
  status: "published" | "already-imported" | "nothing-to-import" | "error";
  snapId?: string;
  error?: string;
  skipped: { path: string; reason: string }[];
  skippedCount?: number;
}

export const backendConfig = callable<[backend: Backend], BackendConfig>("backend_config");
export const setBackendConfig = callable<[backend: Backend, values: Record<string, string | boolean>], BackendConfig>(
  "set_backend_config",
);
export const ludusaviScan = callable<[root: string], { root: string; games: LudusaviGame[] }>("ludusavi_scan");
export const ludusaviImport = callable<
  [root: string, folder: string, backupIds: string[], gameKey: string],
  { gameKey: string; results: ImportResult[] }
>("ludusavi_import");

// Import every game at once: runs in the backend, sends "keepsake_import_progress" after each game.
export type ImportVerdict = "imported" | "already-imported" | "nothing-to-import" | "failed";
export interface ImportAllStatus {
  running: boolean;
  cancelled?: boolean;
  mode?: "latest" | "all";
  done: number;
  total: number;
  current?: string | null;
  games: Record<string, { name: string; status: ImportVerdict; error: string | null; results: ImportResult[] }>;
  summary: Partial<Record<ImportVerdict, number>>;
}
export const ludusaviImportAll = callable<[root: string, mode: "latest" | "all"], ImportAllStatus>("ludusavi_import_all");
export const ludusaviImportCancel = callable<[], ImportAllStatus>("ludusavi_import_cancel");
export const ludusaviImportStatus = callable<[], ImportAllStatus>("ludusavi_import_status");

export type SyncWord ="off" | "not-synced" | "synced" | "pending" | "conflict" | "quarantined";
export type HealthStatus = "ok" | "info" | "warn" | "fail";

export interface QamSummary {
  store: Backend;
  signedIn: boolean;
  deviceName: string;
  lastSync: number | null;
  health: HealthStatus;
  problems: string[];
  conflicts: number;
  enabledGames: number;
  currentGame: { key: string; name: string; status: SyncWord } | null;
  newer?: (NewerSave & { key: string; name: string })[];
  tipsDismissed?: boolean;
  setupComplete: boolean;
  busy: string | null;
}

export interface HealthCheck {
  id: string;
  label: string;
  status: HealthStatus;
  detail: string;
  items: string[];
}

export interface ConflictEntry {
  key: string;
  name: string;
  gameKey: string;
  conflict: SyncConflict;
}

export interface ConflictSide {
  side: "local" | "cloud";
  snapId: string | null;
  device: string | null;
  created: string | null;
  files: number;
  bytes: number;
  changedFiles: number;
  /** ADR-0048: each file added, removed or changed since the last shared save (at most 200). */
  changes?: { path: string; change: "added" | "removed" | "changed" }[];
}

export interface ConflictDetails {
  key: string;
  name: string;
  gameKey: string;
  conflict: SyncConflict | null;
  hasBase?: boolean;
  sides?: ConflictSide[];
}

export interface HistoryItem extends SnapshotSummary {
  key: string;
  name: string;
  gameKey: string;
  quarantined: boolean;
}

export interface PlanEntry {
  key: string;
  name: string;
  action: "push" | "pull" | "adopt" | "conflict" | "up-to-date" | "nothing" | "offline" | "error";
  reason?: string;
}

export interface ConfigSyncInfo {
  gameKey: string | null;
  appliedFrom: string | null;
  appliedAt: number | null;
  pending: boolean;
  concurrent: string[];
}

export const qamSummary = callable<[], QamSummary>("qam_summary");
export const syncNow = callable<[], { ok: boolean; reason?: string; games?: number; counts?: Record<string, number> }>(
  "sync_now",
);
export const listConflicts = callable<[], ConflictEntry[]>("list_conflicts");
export const conflictDetails = callable<[key: string], ConflictDetails>("conflict_details");
export const recentHistory = callable<[limit: number], { snapshots: HistoryItem[]; errors: string[] }>("recent_history");
export const planSync = callable<[keys: string[]], PlanEntry[]>("plan_sync");
export const finishSetup = callable<[keys: string[]], { ok: boolean; enabled: number }>("finish_setup");
export const healthChecks = callable<[probe: boolean], { checks: HealthCheck[]; summary: HealthStatus }>("health_checks");
export const gameConfigSync = callable<[key: string], ConfigSyncInfo>("game_config_sync");

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
  /** The changelog section for `to` (ADR-0049). */
  notes?: string;
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
  method: "manual" | "manual-key" | "steam-id" | "title" | "ambiguous" | "none" | "no-save-data" | "no-manifest";
  title: string | null;
  gameKey: string | null;
  candidates: string[];
}

export interface GameMatch extends MatchInfo {
  key: string;
  name: string;
  kind: "steam" | "shortcut";
  proposal?: { candidate: { gameKey: string; title: string | null } } | null;
  enabled: boolean;
  sync: SyncWord;
  steamCloud: SteamCloud;
  hasRegistry: boolean;
  /** ADR-0049: a newer save from another device, not taken in yet. */
  newer?: NewerSave | null;
}

export interface NewerSave {
  snapId: string;
  device: string | null;
  created: string | null;
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
  gameKey: string | null;
  gameKeySource: "user" | "auto" | null;
  syncRegistry: boolean;
}

export interface IdentitySuggestion {
  gameKey: string;
  title: string | null;
  score: number;
  signals: string[];
  strongSignals: number;
  sources: string[];
}

export interface MatchProposal {
  candidate: IdentitySuggestion;
  alternatives: IdentitySuggestion[];
  raised: number;
}

export const approveMatch = callable<[key: string], GameConfig>("approve_match");
export const rejectMatch = callable<[key: string], { ok: boolean }>("reject_match");
export const setGameKey = callable<[key: string, gameKey: string | null, title: string | null], GameConfig>(
  "set_game_key",
);
export const newGameKey = callable<[key: string], GameConfig>("new_game_key");

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
  /** A checkpoint's name (ADR-0048). */
  label?: string | null;
  pruned?: boolean;
  base?: boolean;
  reasons?: string[];
}

export interface RestoreChange {
  root: string;
  rel: string;
  action: "create" | "replace" | "delete";
  size: number;
}

export interface ActivityEntry {
  time: string | null;
  text: string;
  level: "info" | "warn";
}

export interface SnapshotListing {
  gameKey?: string;
  lastByDevice?: { device: string | null; created: string; kind: string; snapId: string }[];
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
  store: Backend;
  name: string;
  onedriveSignedIn: boolean;
  googleSignedIn: boolean;
  /** ADR-0032: Keepsake's own sign-in client is built in, so no client ID is needed. */
  builtInClient: { onedrive: boolean; gdrive: boolean };
  /** The user has saved their own client, which is used instead of the built-in one. */
  ownClient: { onedrive: boolean; gdrive: boolean };
  /** ADR-0044: which sign-in methods have a client. */
  methods: Record<"onedrive" | "gdrive", Record<SigninMethod, boolean>>;
}

/** The phone (device code) sign-in shows a code; the browser sign-in returns the page to open. */
export type SignInCode =
  | { method?: undefined; userCode: string; verificationUri: string; expiresIn: number }
  | { method: "browser"; authUrl: string; expiresIn: number };

export const cloudStatus = callable<[], CloudStatus>("cloud_status");
export const startSignin = callable<[backend: "onedrive" | "gdrive", method: SigninMethod], SignInCode>("start_signin");
export const cancelSignin = callable<[], { ok: boolean }>("cancel_signin");
export const signOut = callable<[backend?: "onedrive" | "gdrive"], { ok: boolean }>("sign_out");
export const testCloud = callable<[backend?: Backend], { ok: boolean; folder?: string; error?: string; registered?: boolean }>(
  "test_cloud",
);
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
export const snapshotGame = callable<[key: string, label?: string], SnapshotResult>("snapshot_game");
export const listSnapshots = callable<[key: string], SnapshotListing>("list_snapshots");
export const restoreSnapshot = callable<[key: string, snapId: string, paths?: string[]], SnapshotResult>("restore_snapshot");
export interface Playtime {
  totalSeconds: number;
  sessions: number;
  byDevice: { device: string; seconds: number }[];
}
export const gamePlaytime = callable<[key: string], Playtime>("game_playtime");
export const bringNewer = callable<[key: string], { action: string; reason?: string; pending?: boolean }>("bring_newer");
export const restorePreview = callable<[key: string, snapId: string], { snapId: string; changes: RestoreChange[] }>("restore_preview");
export const activity = callable<[limit: number], ActivityEntry[]>("activity");
export const undoRestore = callable<[key: string, prerestoreId: string], SnapshotResult>("undo_restore");
export const pinSnapshot = callable<[key: string, snapId: string], { ok: boolean }>("pin_snapshot");
export const releaseQuarantine = callable<[key: string, snapId: string, confirmed: boolean], SnapshotResult>(
  "release_quarantine",
);
export const runRetention = callable<[key: string], { pruned: string[]; kept: number; orphansDeleted: string[] }>(
  "run_retention",
);
export const manifestStatus = callable<[], ManifestStatus>("manifest_status");
// Sent as "keepsake_manifest_progress" while a refresh runs, and returned by manifestProgress().
export interface ManifestProgress {
  stage: "idle" | "checking" | "downloading" | "indexing" | "saving" | "finished";
  running: boolean;
  bytes?: number;
  total?: number | null;
  entries?: number;
  ok?: boolean;
  reason?: string;
  games?: number;
}
export const manifestProgress = callable<[], ManifestProgress>("manifest_progress");
export const refreshManifest = callable<[force: boolean], { ok: boolean; reason?: string; games?: number }>(
  "refresh_manifest",
);
export const matchGames = callable<[], GameMatch[]>("match_games");
export const searchTitles = callable<[query: string], string[]>("search_titles");
export const getGame = callable<
  [key: string],
  {
    game: GameEntry;
    config: GameConfig;
    match: MatchInfo;
    suggestions: IdentitySuggestion[];
    proposal: MatchProposal | null;
    hasRegistry: boolean;
    steamCloud: SteamCloud;
  }
>("get_game");
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
/** ADR-0044: the Gaming Mode sign-in probe's loopback step. */
export const signinProbe = callable<[action: "start" | "result"], { url?: string; arrived?: boolean; ipv6?: boolean; address?: string; userAgent?: string; listening?: string[]; error?: string }>(
  "signin_probe",
);
export const exportDiagnostics = callable<[frontend: Record<string, unknown>], string>("export_diagnostics");
export const freezeTest = callable<[appid: number, seconds: number], FreezeTestResult>("freeze_test");

// Advisor (slice 14, ADR-0028). Read-only: nothing here changes a setting anywhere (P16).
export interface AdvisorRecommendation {
  source: "deckverified" | "fallback";
  source_url: string;
  report_title?: string;
  report_date: string;
  votes: number;
  device_reported: string;
  device_match: string;
  matchLabel: string;
  confidence: "high" | "medium" | "low";
  workload?: string;
  lines: Record<"power" | "display" | "scaling" | "frame_gen" | "in_game" | "battery", string[]>;
  flags: string[];
  compat: { proton: string | null; launch_options: string | null };
  notes: string;
  launch?: {
    recommended: string;
    current: string;
    where: string;
    flags: string[];
    merged: string | null;
    mergeNotes: string[];
    sameAsCurrent: boolean;
  } | null;
}

export interface AdvisorProton {
  recommended: string;
  force: boolean;
  signal: "report" | "installed";
  signalText: string;
  installNote: string | null;
  current: string;
  matches: boolean;
  where: string;
  asReported: string;
  peer: string;
}

export interface AdvisorView {
  running: boolean;
  settings?: {
    deviceOverride: string;
    workload: "light" | "medium" | "heavy";
    sourceDeckVerified: boolean;
    sourceAntiCheat: boolean;
    sourcePcgw: boolean;
    sourceProtonDb: boolean;
    steamIdOverrides: Record<string, number>;
    stackOverrides: Record<string, string>;
    aiProvider: "" | "anthropic" | "openai" | "gemini";
    aiModel: string;
    aiDailyCap: number;
  };
  current?: {
    power: { tdp_w: number | null; scope: string; note: string | null; tool: string; preset?: string | null } | null;
    framegen: { profile: string | null; multiplier: number | null; tool: string } | null;
  };
  proton?: AdvisorProton | null;
  ai?: {
    providers: { id: "anthropic" | "openai" | "gemini"; name: string; keySet: boolean }[];
    usedToday: number;
    result: { label: string; provider: string; model: string; rec: AdvisorRecommendation | null; discarded: string[]; error: string | null } | null;
  };
  device?: { id: string; name: string; apu: string; how: "detected" | "override" | "generic"; generic: boolean; verified: boolean };
  devices?: { id: string; name: string }[];
  os?: { id: string; pretty: string };
  stack?: {
    detected: { id: string; disabled?: boolean }[];
    selected: Record<string, string>;
    names: Record<string, string>;
    categories: string[];
    options: Record<string, string[]>;
  };
  conflicts?: { kind: string; text: string }[];
  game?: {
    appid: number;
    name: string;
    shortcut: boolean;
    steamAppid: number | null;
    mapping: "steam" | "manifest" | "manual" | "name";
    manifestTitle?: string | null;
    launchOptions?: string;
    compatTool?: string;
  } | null;
  source?: { enabled: boolean; cached: boolean; error: string | null; fetchedAt: number | null };
  anticheat?: {
    enabled: boolean;
    error: string | null;
    entry: { name: string; status: string; meaning: string; blocked: boolean; url: string; attribution: string } | null;
  };
  pcgw?: {
    enabled: boolean;
    error: string | null;
    cached: boolean;
    data: { page: string; url: string; upscaling: string[]; frameGen: string[]; hdr: string | null; rayTracing: string | null; attribution: string } | null;
  };
  pcgwLogin?: boolean;
  /** Keepsake's ProtonDB index (ADR-0035): looked up on the device, never by asking ProtonDB. */
  protondb?: {
    enabled: boolean;
    error: string | null;
    summary: { reports: number; works: number; handheld: number; share: number | null; dump: string; url: string; attribution: string } | null;
  };
  recommendations?: AdvisorRecommendation[];
  attribution?: string[];
}

export const advisorView = callable<[], AdvisorView>("advisor_view");
export const advisorSelectGame = callable<[appid: number], AdvisorView>("advisor_select_game");
export const advisorRefresh = callable<[], AdvisorView>("advisor_refresh");
export const advisorRedetect = callable<[], AdvisorView>("advisor_redetect");
export const advisorSettings = callable<[values: Record<string, unknown>], AdvisorView>("advisor_settings");

export const advisorAiModels = callable<[provider: string], { id: string; label: string }[]>("advisor_ai_models");
export const advisorAiGenerate = callable<[], AdvisorView>("advisor_ai_generate");
// AI keys are kept with the backend secrets; only whether one is set comes back.
export const saveAiKey = callable<[kind: "anthropic" | "openai" | "gemini", values: { apiKey: string }], { configured: boolean }>(
  "set_backend_config",
);

// The PCGamingWiki bot login is kept with the backend secrets; only whether it is set comes back.
export const savePcgwLogin = callable<[kind: "pcgw", values: { username: string; password: string }], { configured: boolean }>(
  "set_backend_config",
);
