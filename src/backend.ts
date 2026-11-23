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
  snapshotStores: Backend[];
  launchPullTimeout: number;
  toastOnSync: boolean;
  idleSyncMinutes: number;
  showSteamApps: boolean;
  setupComplete: boolean;
  registrySync: boolean;
  steamCloudDetection: boolean;
  steamAutoSync: boolean;
  tidyAutomatically: boolean;
  suspendSnapshots: boolean;
  conflictPolicy?: "ask" | "newest";
  libraryBadges?: boolean;
  libraryRoot: string;
  /** ADR-0044: how each provider signs in from Gaming Mode. */
  gamingModeSignin: Record<"onedrive" | "gdrive", SigninMethod>;
  /** ADR-0051: Heroic, Lutris, Bottles and emulators in Games. */
  otherLaunchers?: boolean;
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
  state:
    | "queued"
    | "choose-installer"
    | "creating-shortcut"
    | "run-installer"
    | "choose-game"
    | "retargeting"
    | "done"
    | "failed"
    | "cancelled";
  kind?: "iso" | "folder";
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
  /** ADR-0053: the other ISOs of a disc set, and runtime installers found with the game. */
  otherDiscs?: string[];
  runtimes?: { runtime: string; path: string }[];
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
// Find shares on my network (ADR-0066).
export interface SmbServer {
  name: string;
  address: string;
  url: string;
  via: ("mdns" | "netbios" | "wsd")[];
}
export const installerNetFindSmb = callable<[], { servers: SmbServer[]; methods: Record<string, number | string> }>(
  "installer_net_find_smb",
);
export const installerNetDownload = callable<[access: NetAccess, url: string, title: string, sha256: string], NetDownload>(
  "installer_net_download",
);
export const installerNetCancel = callable<[], NetDownload>("installer_net_cancel");

// Replication: device links and pairing (ADR-0054, ADR-0056).
export interface PairedDevice {
  id: string;
  name: string;
  address: string;
  pairedAt: number;
  lastSeen: number;
  canWake: boolean;
}
export interface Pairing {
  id: string;
  role: "initiator" | "responder";
  address: string;
  // ADR-0070: the requester waits for Accept, then takes the code; the receiver answers, then shows it.
  state: "connecting" | "waiting-accept" | "enter-code" | "request" | "show-code" | "checking" | "paired" | "declined" | "failed" | "cancelled";
  code: string | null;
  peerName: string | null;
  reason: string | null;
}
export interface FoundDevice {
  id: string;
  name: string;
  address: string;
  port: number;
  paired: boolean;
}
export interface ReplicationStatus {
  available: boolean;
  listener: { on: boolean; addresses: string[]; port: number; acceptsRequests: boolean };
  discovery: { on: boolean; problem: string | null };
  peers: PairedDevice[];
  pairings: Pairing[];
  addressChoice: string;
  addressesAvailable: { address: string; kind: "lan" | "overlay" }[];
  thisDevice: { name: string };
}
export interface LinkCheck {
  ok: boolean;
  reason?: string;
  address?: string;
  rttMs?: number;
  slow?: boolean;
  overlay?: boolean;
}
export const replicationStatus = callable<[], ReplicationStatus>("replication_status");
export const replicationSetListener = callable<[on: boolean], ReplicationStatus>("replication_set_listener");
export const replicationSetAddress = callable<[address: string], ReplicationStatus>("replication_set_address");
export const replicationPair = callable<[address: string], Pairing>("replication_pair");
export const replicationAnswer = callable<[pairingId: string, ok: boolean], ReplicationStatus>("replication_answer");
export const replicationEnterCode = callable<[pairingId: string, code: string], ReplicationStatus>("replication_enter_code");
export const replicationCancel = callable<[pairingId: string], ReplicationStatus>("replication_cancel");
export const replicationFind = callable<[], FoundDevice[]>("replication_find");
export const replicationCheck = callable<[peerId: string], LinkCheck>("replication_check");
export const replicationRemove = callable<[peerId: string], ReplicationStatus>("replication_remove");
export const replicationWake = callable<[peerId: string], { sent: number }>("replication_wake");
export interface TransferJob {
  id: string;
  peer: string;
  peers: string[];
  target: string;
  state: "running" | "waiting" | "paused" | "verifying" | "promoting" | "done" | "failed" | "stopped";
  reason: string | null;
  held: boolean;
  total: number;
  received: number;
  megabytesPerSecond: number;
  secondsLeft: number | null;
  streams: number;
}
export interface TransfersStatus {
  jobs: TransferJob[];
  awake: boolean;
  sleepProblem: string | null;
  waitingFor: string | null;
}
export const replicationTransfers = callable<[], TransfersStatus>("replication_transfers");
export const replicationPause = callable<[jobId: string], TransfersStatus>("replication_pause");
export const replicationResume = callable<[jobId: string], TransfersStatus>("replication_resume");
export const replicationStop = callable<[jobId: string], TransfersStatus>("replication_stop");
export interface IncomingOffer {
  id: string;
  title: string;
  from: string;
  peer: string;
  state: "offered" | "transferring" | "registering" | "done" | "failed";
  reason: string | null;
  bytes: number;
  compatTool: string | null;
  toolOffered: boolean;
  droppedOptions: string[];
  appid: number | null;
  update: boolean;
  link: string | null;
}
export interface OffersStatus {
  incoming: IncomingOffer[];
  outgoing: { id: string; title: string; peer: string; created: number; remoteState?: string; remoteReason?: string | null }[];
  sending: Record<string, { state: "preparing" | "sent" | "failed"; title: string; peer: string; reason?: string; warning?: string | null }>;
  activity?: GameTransfer[];
}
export const replicationSend = callable<[key: string, peerId: string], { state: string; title: string; droppedOptions: string[] }>("replication_send");
export const replicationOffers = callable<[], OffersStatus>("replication_offers");
export const replicationOfferCheck = callable<
  [offerId: string, copyTool: boolean],
  { targets?: Record<string, string>; toolMissing?: boolean; problem?: string }
>("replication_offer_check");
export const replicationAccept = callable<[offerId: string, copyTool: boolean], IncomingOffer>("replication_accept");
export const replicationDecline = callable<[offerId: string], OffersStatus>("replication_decline");
export const replicationWithdraw = callable<[offerId: string], OffersStatus>("replication_withdraw");
export const replicationDismiss = callable<[offerId: string], OffersStatus>("replication_dismiss");
export interface GameLink {
  id: string;
  title: string;
  peer: string;
  appid: number | null;
  policy: "off" | "manual" | "auto";
  state: "in-sync" | "changed-here" | "update-available" | "both-changed" | "updating";
  checked: number;
}
export const replicationGames = callable<[], GameLink[]>("replication_games");
export interface DeviceCheck {
  id: string;
  title: string;
  needs: "one" | "both";
}
export interface DeviceCheckResult extends DeviceCheck {
  status: "pass" | "warn" | "fail" | "skip";
  found: string;
  at: number;
}
export const deviceChecks = callable<[], { checks: DeviceCheck[]; results: DeviceCheckResult[] }>("device_checks");
export const deviceCheckRun = callable<[id: string], DeviceCheckResult>("device_check_run");
export const deviceChecksRunAll = callable<[], { checks: DeviceCheck[]; results: DeviceCheckResult[] }>("device_checks_run_all");
export const deviceChecksExport = callable<[], { file: string; where: string; summary: string }>("device_checks_export");
export const directSyncNow = callable<[], { peers: number; copied: number; removed: number; unreachable: string[] }>("direct_sync_now");
export const replicationSetPolicy = callable<[linkId: string, policy: string], GameLink[]>("replication_set_policy");
export const replicationCheckGame = callable<[linkId: string], GameLink>("replication_check_game");
export const replicationSendUpdate = callable<[linkId: string], GameLink[]>("replication_send_update");
export const replicationApplyUpdate = callable<[offerId: string, takeTheirs: boolean], IncomingOffer>("replication_apply_update");
export const replicationKeepMine = callable<[offerId: string], OffersStatus>("replication_keep_mine");
export const replicationRemoveGame = callable<[offerId: string], OffersStatus>("replication_remove_game");

// A game moving between devices, as one bar on either device (v0.31.0, ADR-0072).
export type TransferStage = "checking-space" | "preparing" | "copying" | "verifying" | "adding" | "done" | "failed" | "paused" | "waiting";
export type GameTransfer = {
  id: string;
  direction: "sending" | "receiving";
  title: string;
  peer: string;
  stage: TransferStage;
  done: number;
  total: number;
  percent: number;
  bytesPerSecond: number;
  secondsLeft: number | null;
  reason: string | null;
  update: boolean;
  canStop: boolean;
  canClear: boolean;
};
export const replicationActivity = callable<[], GameTransfer[]>("replication_activity");

// "When saves differ: take the newest" (R16 step 2, ADR-0080).
export interface NewestChoice {
  choice: "use-cloud" | "use-local";
  used: string | null;
  replaced: string | null;
  device: string | null;
  margin: number | null;
  at: number;
}
// R18 (ADR-0081): the badge in Steam's library, and artwork for streaming tiles.
export const libraryBadge = callable<[appid: number], { state: string; label: string; detail?: string } | null>("library_badge");

// Artwork for any non-Steam game (R29 stage 2, ADR-0093): only the kinds it has none of.
export const gameArtStatus = callable<[key: string], { nonSteam: boolean; missing: string[]; available: boolean }>("game_art_status");
export const gameArtApply = callable<[key: string, gameId: number], { queued: number }>("game_art_apply");
export const installerStreamTiles = callable<[], { appid: number; name: string; devices: string[] }[]>("installer_stream_tiles");
export const installerStreamArtSearch = callable<[title: string], { id: number; name: string; verified: boolean }[]>("installer_stream_art_search");
export const installerStreamArtApply = callable<[appid: number, gameId: number], { queued: number }>("installer_stream_art_apply");

export const takeNewest = callable<[key: string], Record<string, unknown>>("take_newest");
export const newestChoice = callable<[key: string], NewestChoice | null>("newest_choice");
export const undoNewest = callable<[key: string], Record<string, unknown>>("undo_newest");
export const snapshotLocations = callable<[key: string], Record<string, string[]>>("snapshot_locations");

// This handheld, for Device's Status tab (layout v3, ADR-0073).
export interface DeviceStatus {
  model: string;
  vendor: string;
  profile: string;
  how: "detected" | "generic" | "override";
  apu: string;
  tdp: { min?: number; max?: number; default?: number };
  display: { width?: number | null; height?: number | null; refresh_hz_max?: number | null; vrr?: boolean };
  facts: Record<string, string>;
  battery: { percent: number | null; mains: boolean | null; present: boolean };
}
export const deviceStatus = callable<[], DeviceStatus>("device_status");

// Live readings (R21 stage 1, ADR-0074): every world-readable sensor, read-only.
export interface Sensor {
  label: string;
  value: number;
}
export interface DeviceReadings {
  chips: { name: string; temps: Sensor[]; fans: Sensor[]; power: Sensor[] }[];
  battery: { percent?: number | null; status?: string | null; watts?: number | null; mains?: boolean; chargeLimit?: number };
  gpuWatts: number | null;
  bios: { version: string | null; date: string | null };
  profile: { current: string; choices: string[]; words: string } | null;
  cpu: { boost: boolean | null; smt: string | null; online: number | null };
}
export const deviceReadings = callable<[], DeviceReadings>("device_readings");

// Performance profiles (R21 stage 2, ADR-0076): through steamos-manager only, per game.
export interface PowerLimitValues {
  spl: number;
  sppt: number;
  fppt: number;
}
export interface PerformanceValues {
  mode?: string;
  tdp?: number;
  boost?: boolean;
  limits?: PowerLimitValues;
}
export interface PerformanceStatus {
  available: boolean;
  off?: boolean;
  problem: string | null;
  current: {
    tdp: { value: number; min: number; max: number } | null;
    profile: { current: string; available: string[]; suggested: string } | null;
    boost: boolean | null;
    chargeLimit: { value: number; minimum: number } | null;
  } | null;
  tools: string[];
  game: number | null;
  profile: PerformanceValues | null;
  applied: PerformanceValues;
  stopped: string | null;
  limits: { min?: number; max?: number };
  // Separate SPL, SPPT and FPPT (ADR-0084): ranges from the firmware; setting needs the helper.
  powerLimits?: {
    available: boolean;
    ready: boolean;
    ranges: Record<keyof PowerLimitValues, { current: number; min: number; max: number; step: number }> | null;
  };
}
export const devicePerformance = callable<[], PerformanceStatus>("device_performance");
export const deviceApply = callable<[values: PerformanceValues, saveFor: number | null], PerformanceStatus>("device_apply");
export const deviceForget = callable<[appid: number], PerformanceStatus>("device_forget");

// The 80 percent charge limit (R21 stage 4, ADR-0077).
export interface ChargeLimitStatus {
  control: "steamos-manager" | null;
  limited: boolean | null;
  level: number | null;
  firmware: { battery: string | null; chargeTypes: string | null; threshold: number | null; limited: boolean | null };
  problem?: string | null;
  where?: string;
}
export const deviceBattery = callable<[], ChargeLimitStatus>("device_battery");

// The controllers, read-only (R21 stage 5, ADR-0078).
export interface ControllersStatus {
  batteries: { name: string; percent: number | null; level: string | null; status: string | null }[];
  controllers: { id: string; settings: Record<string, string>; left: Record<string, string>; right: Record<string, string>; touchpad: Record<string, string> }[];
  rings: Record<string, string> | null;
  tools: string[];
}
export const deviceControllers = callable<[], ControllersStatus>("device_controllers");

// Changing the controllers and the stick lights (R24, ADR-0086), through the Haversack Helper.
export interface ControllerSettingsStatus {
  off?: boolean;
  problem: string | null;
  present?: boolean;
  current?: Record<string, string> | null;
  kept: Record<string, unknown>;
  allowed: string[];
  tools: { hhd?: boolean; inputplumber?: boolean };
  helper: { installed?: boolean; ready?: boolean; problem?: string };
}
export const controllerSettingsStatus = callable<[], ControllerSettingsStatus>("controller_settings_status");
export const controllerSettingsSet = callable<[values: Record<string, unknown>, keep: boolean], ControllerSettingsStatus>("controller_settings_set");
export const controllerSettingsForget = callable<[], ControllerSettingsStatus>("controller_settings_forget");

// Controller reconnect help (R22, ADR-0082): every paired device, help per device by adapter and address.
export const RECONNECT_EVENT = "keepsake_reconnect";
export interface ReconnectDiagnosis {
  outcome: string;
  title: string;
  advice: string;
  recommend: string | null;
  evidence: string[];
  sixaxis: boolean;
  at: number;
  journal?: string;
  capture?: string;
}
export interface ReconnectDevice {
  adapter: string;
  adapterName: string;
  mac: string;
  name: string;
  class: string | null;
  modalias: string | null;
  icon: string | null;
  transport: "bredr" | "le" | "unknown";
  paired: boolean;
  connected: boolean;
  services: number;
  unregisteredPrefix: boolean;
  help: boolean;
  commit: boolean;
  fullMode: boolean;
  last: ReconnectDiagnosis | null;
  suggest: { reason: string; at: number } | null;
  captured: boolean;
  stored?: { record: boolean; linkKey: boolean; keyType: number | null; trusted: boolean; cache: boolean; services: boolean; backups: number } | null;
}
export interface ReconnectStatus {
  available: boolean;
  problem: string | null;
  off?: boolean;
  adapters?: { address: string; name: string; alias: string; powered: boolean }[];
  devices?: ReconnectDevice[];
  dryRun?: boolean;
  watcher?: boolean;
  cableReady?: boolean;
  helper?: { installed: boolean; ready: boolean; problem?: string; version?: string; helper?: string };
  sspGate?: { on: boolean; adapter: string | null; state: string };
  actions?: { at: string; action: string; device: string | null; [k: string]: unknown }[];
}
export interface ReconnectResult {
  ok: boolean;
  state: string;
  message: string;
}
export const reconnectStatus = callable<[], ReconnectStatus>("reconnect_status");
export const reconnectSetHelp = callable<[adapter: string, mac: string, on: boolean, label: string], ReconnectStatus>("reconnect_set_help");
export const reconnectSetOption = callable<[adapter: string, mac: string, option: "commit" | "fullMode", on: boolean], ReconnectStatus>("reconnect_set_option");
export const reconnectSetDryRun = callable<[on: boolean], ReconnectStatus>("reconnect_set_dry_run");
export const reconnectDismiss = callable<[adapter: string, mac: string], ReconnectStatus>("reconnect_dismiss");
export const reconnectAssist = callable<[adapter: string, mac: string], ReconnectResult>("reconnect_assist");
export const reconnectReadUsb = callable<
  [adapter: string, mac: string],
  { read: { ok: boolean; state?: string; message?: string; family?: string; storesThisHandheld?: boolean }; diagnosis: ReconnectDiagnosis | null }
>("reconnect_read_usb");
export const reconnectDiagnose = callable<[adapter: string, mac: string], ReconnectDiagnosis>("reconnect_diagnose");
export const reconnectCablePair = callable<[adapter: string, mac: string, order: "same" | "reversed"], ReconnectResult & { backup?: string; sixaxis?: boolean }>(
  "reconnect_cable_pair",
);
export const reconnectCableRestore = callable<[adapter: string, mac: string], { ok: boolean; restored: string }>("reconnect_cable_restore");
export const reconnectSetSspGate = callable<[on: boolean, adapter: string, confirm: string], ReconnectStatus>("reconnect_set_ssp_gate");
export const reconnectSspConfirm = callable<[], ReconnectStatus>("reconnect_ssp_confirm");
export const helperPrepare = callable<[], PreparedUpdate>("helper_prepare");
export const reconnectExport = callable<[adapter: string, mac: string, redactAdapter: boolean], { file: string; where: string }>("reconnect_export");

// Stage 6 (ADR-0079): Wi-Fi power saving and the BIOS check.
export interface DeviceExtras {
  wifiPowerSaving: boolean | null;
  bios: { version: string | null; date: string | null; known?: boolean; model?: string; notes: string[]; level: "ok" | "warn" | "fail" };
}
export const deviceExtras = callable<[], DeviceExtras>("device_extras");
export const deviceSetWifiPowerSaving = callable<[on: boolean], DeviceExtras>("device_set_wifi_power_saving");
export const deviceSetChargeLimit = callable<[on: boolean], ChargeLimitStatus>("device_set_charge_limit");
export const replicationStopGame = callable<[entryId: string], GameTransfer[]>("replication_stop_game");
export const replicationClearGame = callable<[entryId: string], GameTransfer[]>("replication_clear_game");
export const replicationPeerGames = callable<[peerId: string], { id: string; title: string }[]>("replication_peer_games");
export const replicationGetGame = callable<[peerId: string, gameId: string, title: string], GameTransfer[]>("replication_get_game");

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
export const installerStart = callable<[source: string, title: string, queue?: boolean], InstallJob>("installer_start");
export const installerSwapDisc = callable<[jobId: number, disc: string], InstallJob>("installer_swap_disc");
export const installerCreateShortcut = callable<[jobId: number, installer: string], InstallJob>("installer_create_shortcut");
export const installerFinishedInstalling = callable<[jobId: number], InstallJob>("installer_finished_installing");
export const installerRetarget = callable<[jobId: number, exe: string], InstallJob>("installer_retarget");
export const installerCancel = callable<[jobId: number], InstallJob>("installer_cancel");

export const modulesStatus = callable<[], ModulesStatus>("modules_status");
// Emulator games (R26 stage 1, ADR-0087): this device's setup, read-only.
export interface EmulatorSetup {
  off?: boolean;
  problem?: string;
  setups: string[];
  emulators: { name: string; system: string; type: "appimage" | "binary" | "flatpak" }[];
  games: { system: string; name: string; files: number; size: number }[];
  perSystem: Record<string, number>;
  secrets: Record<string, number>;
}
export const emulatorSetup = callable<[], EmulatorSetup>("emulator_setup");
export const emulatorSend = callable<[peerId: string, system: string, unit: string, withKeys: boolean], { ok: boolean; parts: string[] }>(
  "emulator_send",
);

// Quick menu shortcuts (layout v3 addendum, ADR-0073): pages, actions and status lines, chosen and ordered.
export const SHORTCUTS_EVENT = "keepsake_shortcuts";
export interface Shortcut {
  id: string;
  kind: "page" | "action" | "status";
  label: string;
  module: string;
  feature?: string;
  open?: [string, string];
}
export interface QamShortcuts {
  available: Shortcut[];
  shown: Shortcut[];
  chosen: string[];
  defaults: string[];
}
export const qamShortcuts = callable<[], QamShortcuts>("qam_shortcuts");
export const runShortcut = callable<[shortcutId: string], { message: string; open?: [string, string] }>("run_shortcut");

// Fan control (R24, ADR-0085): curves for the Legion Go 2, full speed for the Legion Go, through the helper.
export type FanPoint = [number, number];
export interface FansStatus {
  off?: boolean;
  problem: string | null;
  helper: { installed?: boolean; ready?: boolean; problem?: string };
  temperature: number | null;
  mode: string | null;
  game?: number | null;
  device: {
    model?: "go2" | "go2-beta" | "go1" | null;
    rpm?: number | null;
    override?: number | null;
    firmware?: { bios: string; ec: string } | null;
    validated?: boolean;
    conflicts?: string[];
    acpiCall?: boolean;
    fullSpeedAttribute?: boolean;
    controlling?: boolean;
    problem?: string;
  };
  tools: string[];
  settings: {
    enabled: boolean;
    fullSpeed: boolean;
    unlocked: boolean;
    smooth: boolean;
    profiles: Record<string, FanPoint[]>;
    default: string;
    modes: Record<string, string>;
    games: Record<string, string>;
  };
  active: string | null;
  target: number | null;
  limits: { min: number; max: number; failsafe: number };
}
export const fansStatus = callable<[], FansStatus>("fans_status");
export const fansSetOptions = callable<
  [options: { enabled?: boolean; fullSpeed?: boolean; smooth?: boolean; unlocked?: boolean; confirm?: string }],
  FansStatus
>("fans_set_options");
export const fansSaveProfile = callable<[name: string, points: FanPoint[], makeDefault: boolean], FansStatus>("fans_save_profile");
export const fansDeleteProfile = callable<[name: string], FansStatus>("fans_delete_profile");
export const fansAssign = callable<[kind: "default" | "mode" | "game", key: string, name: string | null], FansStatus>("fans_assign");
export const fansHandBack = callable<[], FansStatus>("fans_hand_back");
export const fansSelftest = callable<[], { passed: boolean; status: FansStatus }>("fans_selftest");

// The navigation recorder (v0.41.1): one file in the settings folder, also in the Device checks export.
export const saveNavigationRecord = callable<
  [record: { summary: Record<string, number>; events: { t: number; kind: string; detail?: Record<string, string | number | boolean> }[] }],
  { file: string; where: string }
>("save_navigation_record");
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

export type Backend = "local" | "onedrive" | "gdrive" | "webdav" | "s3" | "direct";

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

export type GameKind = "steam" | "shortcut" | "heroic" | "lutris" | "bottles" | "emulator";

export interface GameEntry {
  key: string;
  kind: GameKind;
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
  /** ADR-0051: a plain Wine prefix (Heroic, Lutris, Bottles), and an emulator's optional save-state folders. */
  wine_prefix?: string | null;
  emulator?: string;
  states_paths?: CustomPath[];
  /** ADR-0064: shortcuts only; "remote" is a Steam Remote Play entry for a game on another device. */
  presence?: "local" | "remote" | "unsure";
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
  kind: GameKind;
  proposal?: { candidate: { gameKey: string; title: string | null } } | null;
  enabled: boolean;
  sync: SyncWord;
  steamCloud: SteamCloud;
  /** ADR-0063: who last switched sync: never, the user, or Haversack for a Steam game without Steam Cloud. */
  enabledSource?: "user" | "auto" | null;
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
  /** ADR-0063: who last switched sync. */
  enabledSource?: "user" | "auto" | null;
  /** ADR-0071: the save locations this game uses; null means all of them. */
  locations?: Backend[] | null;
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
  /** ADR-0050: snapshots the integrity check found damaged or missing in the cloud. */
  damaged?: string[];
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
  directReady?: boolean;
  direct?: { peers: number; copied: number; unreachable: string[]; at: number } | null;
  /** ADR-0032: Haversack's own sign-in client is built in, so no client ID is needed. */
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
export interface ScrubReport {
  lastRun: number;
  full: boolean;
  games: Record<string, { name: string; checked: number; bad: string[]; missing: string[]; error?: string }>;
}
export interface StoragePart {
  bytes: number;
  files: number;
  partial: boolean;
  present: boolean;
  insidePrefix?: boolean;
}
export interface StorageRow {
  key: string;
  name: string;
  install: StoragePart;
  prefix: StoragePart;
  shaderCache: StoragePart;
  saves: { bytes: number };
  totalBytes: number;
  partial: boolean;
  canClearShaderCache: boolean;
  canResetPrefix: boolean;
  reset?: { stage: "waiting" | "restored"; started: number } | null;
}
export const storageUsage = callable<[key: string | null], { games: StorageRow[]; notMeasured: number }>("storage_usage");
export const clearShaderCache = callable<[key: string], { ok: boolean; freed: number }>("clear_shader_cache");
export const resetPrefix = callable<[key: string], { ok: boolean; stage: string }>("reset_prefix");
export const cancelPrefixReset = callable<[key: string], { ok: boolean }>("cancel_prefix_reset");
export const deleteOldPrefix = callable<[key: string], { ok: boolean; freed: number }>("delete_old_prefix");
export const scrubCloud = callable<[full: boolean], ScrubReport>("scrub_cloud");
export const repairSnapshot = callable<[key: string], SnapshotResult>("repair_snapshot");
export const exportSnapshots = callable<
  [folder: string, scope: "latest" | "all", key?: string | null],
  { ok: boolean; folder: string; games: number; snapshots: number }
>("export_snapshots");
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

// Games you can stream from another device: Steam Remote Play's entries (ADR-0064).
export interface RemoteCopyReport {
  appid: number;
  name: string;
  steam: "local" | "remote" | "unsure";
  clients: string[];
  hidden: boolean;
}
export interface RemoteCopy {
  appid: number;
  name: string;
  presence: "remote" | "unsure";
  from: string[];
  clash: boolean;
  hidden: boolean;
}
export interface RemoteCopiesStatus {
  reportAt: number | null;
  copies: RemoteCopy[];
  log: Record<string, { name: string; state: "pending" | "hidden" | "failed" | "undone" | "came-back"; at: number }>;
  automatic: boolean;
  tidyAvailable: boolean;
  newlyHidden: { appid: number; name: string }[];
}
export const remoteCopiesReport = callable<[entries: RemoteCopyReport[]], { newlyHidden: { appid: number; name: string }[]; tidied: number }>(
  "remote_copies_report",
);
export const remoteCopiesStatus = callable<[], RemoteCopiesStatus>("remote_copies_status");
export const tidyCopies = callable<[appids: number[]], { queued: number }>("tidy_copies");
export const undoTidy = callable<[], { queued: number }>("undo_tidy");
export const unhideLocal = callable<[appid: number], { id: number }>("unhide_local");
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
  sessions?: AdvisorSessions;
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
  /** Haversack's ProtonDB index (ADR-0035): looked up on the device, never by asking ProtonDB. */
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

// Uninstall (ADR-0065).
export interface UninstallPlan {
  key: string;
  name: string;
  kind: GameKind;
  appid: number;
  synced: boolean;
  gameKey: string | null;
  steam: boolean;
  store?: string;
  folders: { path: string; kind: "prefix" | "install"; size: number; freeAfter: number }[];
  kept: { path: string; reason: string }[];
}
export interface UninstallJob {
  key: string;
  name: string;
  appid: number;
  state: "starting" | "backing-up" | "removing-shortcut" | "deleting" | "cleaning" | "done" | "failed" | "cancelled";
  folders: UninstallPlan["folders"];
  kept: UninstallPlan["kept"];
  done: number;
  total: number;
  removed: string[];
  error: string | null;
  backup: string | null;
  restoreFrom: string | null;
}
export const uninstallPlan = callable<[key: string], UninstallPlan>("uninstall_plan");
export const uninstallStart = callable<[key: string, skipBackup: boolean], UninstallJob>("uninstall_start");
export const uninstallSteam = callable<[key: string, backup: boolean], { op: number; backup: unknown }>("uninstall_steam");
export const uninstallStatus = callable<[], UninstallJob | null>("uninstall_status");
export const uninstallCancel = callable<[], UninstallJob | null>("uninstall_cancel");

// How each game ran on this device (ADR-0069).
export interface AdvisorSession {
  start: number;
  end: number;
  seconds: number;
  power: "plugged in" | "on battery" | "mixed";
  fps?: { source: "steam" | "mangohud" | null; avg?: number; min5s?: number | null; low1?: number; low01?: number };
  watts?: { socketAvg: number | null; socketPeak: number | null; cpuAvg: number | null; cpuPeak: number | null; gpuAvg: number | null; gpuPeak: number | null };
  battery?: { drainW?: number; percentPerHour?: number; lifeHours?: number };
  cpu?: { busyAvg: number | null; mhzAvg: number | null; tempAvg: number | null; tempPeak: number | null };
  gpu?: { busyAvg: number | null; mhzAvg: number | null; tempAvg: number | null; tempPeak: number | null };
  memory?: { ramPeakMiB: number | null; vramPeakMiB: number | null };
  throttle?: { seen: boolean; afterMinutes: number | null };
  settings?: { tdp: number | null; tdpTool: string | null; frameCap: number | null; protonVersion: string | null; frameGen: string | null };
}
export interface AdvisorSessions {
  last: AdvisorSession | null;
  recent: AdvisorSession[];
  total: { sessions: number; seconds: number; fpsAvg?: number } | null;
  advice: { id: string; text: string; source: string; measured: boolean }[];
}
export const advisorPerfSample = callable<[diagnosticB64: string], { ok: boolean; fps?: number | null }>("advisor_perf_sample");
export const onResume = callable<[], { ok: boolean }>("on_resume");

// Several save locations (ADR-0071).
export interface SaveLocation {
  id: Backend;
  lastOk?: number;
  problem?: string | null;
  missing?: number;
  bytes?: number;
}
export interface LocationsStatus {
  locations: SaveLocation[];
  available: Backend[];
}
export const locationsStatus = callable<[], LocationsStatus>("locations_status");
export const addLocation = callable<[backend: Backend], LocationsStatus>("add_location");
export const removeLocation = callable<[backend: Backend], LocationsStatus>("remove_location");
export const setGameLocations = callable<[key: string, names: Backend[] | null], GameConfig>("set_game_locations");

// Haversack becomes Haversack (ADR-0089): held while the old plugin is installed, then its data moves across.
export interface RenameStatus {
  moved: { from: string; at?: string; files?: number } | null;
  oldInstalled: boolean;
  oldHelper: boolean;
  hold: boolean;
  started: boolean;
  error: string;
}
export const renameStatus = callable<[], RenameStatus>("rename_status");
export const renameFinish = callable<[], RenameStatus>("rename_finish");

// Looks (R29 stage 1, ADR-0091): boot and suspend animations, and the theme plugins read only.
export type AnimationKind = "boot" | "suspend" | "throbber";
export interface LooksStatus {
  enabled: boolean;
  animations: {
    videos: Record<AnimationKind, { who: "steam" | "haversack" | "other"; name: string | null; keptOriginal: boolean }>;
    blockedBy: string | null;
    steamFound: boolean;
  };
  choices: { id: string; name: string; from: string; bytes: number }[];
  sendable: Record<"themes" | "sounds" | "animations", number>;
  plugins: { css: boolean; audio: boolean; animations: boolean };
  themes: { name: string; author: string; version: string; preset: boolean }[];
  sounds: { name: string; author: string; music: boolean }[];
}
export const looksStatus = callable<[], LooksStatus>("looks_status");
export const looksSetAnimation = callable<[kind: AnimationKind, choice: string], LooksStatus["animations"]>("looks_set_animation");
export const looksResetAnimation = callable<[kind: AnimationKind], LooksStatus["animations"]>("looks_reset_animation");
export type LooksPart = "themes" | "sounds" | "animations";
export const looksSend = callable<[peerId: string, parts: LooksPart[]], { sending: string }>("looks_send");

// Pause the running game (R29 stage 3, ADR-0094): until Resume, at most an hour.
export interface PauseStatus {
  available: boolean;
  game: number | null;
  paused: boolean;
  since: number | null;
  limitMinutes: number;
}
export const gamePauseStatus = callable<[], PauseStatus>("game_pause_status");
export const gamePause = callable<[], PauseStatus>("game_pause");
export const gameResume = callable<[], PauseStatus>("game_resume");

// Which games are on which SD card or drive, including cards not inserted (R29 stage 4, ADR-0096).
export interface SdCard {
  label: string;
  inserted: boolean;
  lastSeen: number | null;
  games: string[];
  shortcuts: string[];
}
export const sdCards = callable<[], SdCard[]>("sd_cards");
