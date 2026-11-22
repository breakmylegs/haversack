// The parts of the backend's answers the desktop interface reads. They mirror src/backend.ts, which the
// Decky interface uses; both talk to the same KeepsakeApp (ADR-0038).

export type HealthStatus = "ok" | "info" | "warn" | "fail";

export interface QamSummary {
  store: string;
  signedIn: boolean;
  deviceName: string;
  lastSync: number | null;
  health: HealthStatus;
  problems: string[];
  conflicts: number;
  enabledGames: number;
  currentGame: { key: string; name: string; status: string } | null;
  newer?: (NewerSave & { key: string; name: string })[];
  setupComplete: boolean;
  busy: string | null;
}

export interface HeadSummary {
  snapId: string;
  device: string | null;
  created: string;
}

export interface ConflictEntry {
  key: string;
  name: string;
  gameKey: string;
  conflict: { kind: "adoption" | "fork" | "both-changed"; heads: HeadSummary[]; localFiles: number; raised: number };
}

export interface ConflictSide {
  side: "local" | "cloud";
  snapId: string | null;
  device: string | null;
  created: string | null;
  files: number;
  bytes: number;
  changedFiles: number;
  changes?: { path: string; change: "added" | "removed" | "changed" }[];
}

export interface ConflictDetails {
  key: string;
  name: string;
  gameKey: string;
  conflict: ConflictEntry["conflict"] | null;
  hasBase?: boolean;
  sides?: ConflictSide[];
}

export interface HistoryItem {
  key: string;
  name: string;
  gameKey: string;
  snapId: string;
  created: string;
  kind: string;
  device: string | null;
  files: number;
  bytes: number;
  quarantined: boolean;
}

export interface HealthCheck {
  id: string;
  label: string;
  status: HealthStatus;
  detail: string;
  items: string[];
}

export interface ModuleStatus {
  name: string;
  title: string;
  description: string;
  writes: string;
  available: boolean;
  unavailableReason: string | null;
  flag: boolean;
  running: boolean;
  failed: string | null;
}

export interface ReleaseInfo {
  tag: string;
  version: string;
  prerelease: boolean;
  desktop_url: string | null;
}

export interface UpdateCheck {
  current: string;
  latest: ReleaseInfo | null;
  updateAvailable: boolean;
  error: string | null;
}

export interface PcUpdateStatus {
  installed: boolean;
  running: string;
  current: string | null;
  previous: string | null;
  busy: string | null;
}

export interface PcResult {
  ok: boolean;
  reason?: string;
  detail?: string;
  version?: string;
}

export interface CloudStatus {
  store: string;
  name: string;
  problem: string | null;
  onedriveSignedIn: boolean;
  googleSignedIn: boolean;
  methods?: Record<"onedrive" | "gdrive", { browser: boolean; phone: boolean }>;
  directReady?: boolean;
  direct?: { peers: number; copied: number; unreachable: string[]; at: number } | null;
}

export interface GameMatch {
  key: string;
  name: string;
  kind: string;
  method: string;
  title: string | null;
  gameKey: string | null;
  candidates: string[];
  proposal?: { candidate: { gameKey: string; title: string | null } } | null;
  enabled: boolean;
  sync: string;
  newer?: NewerSave | null;
}

export interface NewerSave {
  snapId: string;
  device: string | null;
  created: string | null;
}

export interface Settings {
  conflictPolicy?: "ask" | "newest";
  deviceName: string;
  updateChannel: "stable" | "prerelease";
  idleSyncMinutes: number;
  toastOnSync: boolean;
  gateMaxRemovedPercent: number;
  gateMaxSizeDropPercent: number;
  readOnly: boolean;
}

export interface LudusaviGame {
  name: string;
  backups: unknown[];
  error: string | null;
  inManifest: boolean;
}

export interface ImportAllStatus {
  running: boolean;
  cancelled?: boolean;
  done: number;
  total: number;
  current?: string | null;
  summary: Record<string, number>;
}

export interface ActivityEntry {
  time: string | null;
  text: string;
  level: "info" | "warn";
}

// Replication (ADR-0054, ADR-0056).
export interface PairedDevice {
  id: string;
  name: string;
  address: string;
  lastSeen: number;
  canWake: boolean;
}
export interface Pairing {
  id: string;
  address: string;
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
  addressesAvailable: { address: string; kind: string }[];
}
export interface LinkCheck {
  ok: boolean;
  reason?: string;
  address?: string;
  rttMs?: number;
  slow?: boolean;
  overlay?: boolean;
}
export interface TransferJob {
  id: string;
  target: string;
  state: string;
  reason: string | null;
  total: number;
  received: number;
  megabytesPerSecond: number;
  secondsLeft: number | null;
}
export interface TransfersStatus {
  jobs: TransferJob[];
  awake: boolean;
  sleepProblem: string | null;
  waitingFor: string | null;
}
export interface IncomingOffer {
  id: string;
  title: string;
  from: string;
  state: string;
  reason: string | null;
  bytes: number;
  compatTool: string | null;
  toolOffered: boolean;
  droppedOptions: string[];
  update?: boolean;
}
export interface OffersStatus {
  incoming: IncomingOffer[];
  outgoing: { id: string; title: string; peer: string; created: number; remoteState?: string; remoteReason?: string | null }[];
  sending: Record<string, { state: string; title: string; peer: string; reason?: string; warning?: string | null }>;
  activity?: GameTransfer[];
}
// A game moving between devices, as one bar on either device (v0.31.0, ADR-0072).
export interface GameTransfer {
  id: string;
  direction: "sending" | "receiving";
  title: string;
  peer: string;
  stage: "checking-space" | "preparing" | "copying" | "verifying" | "adding" | "done" | "failed" | "paused" | "waiting";
  done: number;
  total: number;
  percent: number;
  bytesPerSecond: number;
  secondsLeft: number | null;
  reason: string | null;
  update: boolean;
  canStop: boolean;
  canClear: boolean;
}
export interface GameLink {
  id: string;
  title: string;
  appid: number | null;
  policy: string;
  state: string;
}

// Layout v3 (ADR-0073): what the new desktop pages read.
export interface DeviceStatusDesk {
  model: string;
  vendor: string;
  profile: string;
  how: string;
  apu: string;
  tdp: { min?: number; max?: number };
  battery: { percent: number | null; mains: boolean | null; present: boolean };
}
export interface DeviceCheckDesk {
  id: string;
  title: string;
  needs: "one" | "both";
}
export interface DeviceCheckResultDesk extends DeviceCheckDesk {
  status: "pass" | "warn" | "fail" | "skip";
  found: string;
}
export interface LogRecordDesk {
  ts: string;
  level: string;
  event: string;
  msg: string;
}
export interface AdvisorSessionDesk {
  start: number;
  watts?: { socketAvg: number | null; socketPeak: number | null };
  cpu?: { tempPeak: number | null };
  gpu?: { tempPeak: number | null };
  fps?: { avg?: number; low1?: number };
  battery?: { percentPerHour?: number };
}
export interface AdvisorDesk {
  running: boolean;
  game?: { name: string } | null;
  recommendations?: { lines: { power: string[]; display: string[]; scaling: string[] } }[];
  sessions?: { recent: AdvisorSessionDesk[]; advice: { text: string }[] };
}
export interface SensorDesk {
  label: string;
  value: number;
}
export interface DeviceReadingsDesk {
  chips: { name: string; temps: SensorDesk[]; fans: SensorDesk[]; power: SensorDesk[] }[];
  battery: { watts?: number | null };
  bios: { version: string | null; date: string | null };
  profile: { current: string; choices: string[]; words: string } | null;
  cpu: { boost: boolean | null; smt: string | null; online: number | null };
}
export interface PerformanceDesk {
  available: boolean;
  off?: boolean;
  problem: string | null;
  current: {
    tdp: { value: number; min: number; max: number } | null;
    profile: { current: string; available: string[] } | null;
    boost: boolean | null;
  } | null;
  tools: string[];
  game: number | null;
  profile: Record<string, unknown> | null;
  stopped: string | null;
  limits: { min?: number; max?: number };
  powerLimits?: {
    available: boolean;
    ready: boolean;
    ranges: Record<"spl" | "sppt" | "fppt", { current: number; min: number; max: number; step: number }> | null;
  };
}
// Quick menu shortcuts (ADR-0073 addendum).
export interface ShortcutDesk {
  id: string;
  kind: "page" | "action" | "status";
  label: string;
}
export interface QamShortcutsDesk {
  available: ShortcutDesk[];
  chosen: string[];
  defaults: string[];
}
// Fan control (ADR-0085).
export interface FansDesk {
  off?: boolean;
  problem: string | null;
  helper: { ready?: boolean };
  temperature: number | null;
  mode: string | null;
  game?: number | null;
  device: { model?: string | null; rpm?: number | null; firmware?: { bios: string; ec: string } | null; validated?: boolean; conflicts?: string[]; fullSpeedAttribute?: boolean; controlling?: boolean };
  tools: string[];
  settings: { enabled: boolean; fullSpeed: boolean; unlocked: boolean; smooth: boolean; profiles: Record<string, [number, number][]>; default: string };
  active: string | null;
  target: number | null;
  limits: { min: number; max: number; failsafe: number };
}
export interface ChargeLimitDesk {
  control: string | null;
  limited: boolean | null;
  firmware: { chargeTypes: string | null };
  where?: string;
}
export interface ControllersDesk {
  batteries: { name: string; percent: number | null; level: string | null; status: string | null }[];
  controllers: { id: string; settings: Record<string, string>; left: Record<string, string>; right: Record<string, string>; touchpad: Record<string, string> }[];
  rings: Record<string, string> | null;
  tools: string[];
}
// Controller reconnect help (ADR-0082, ADR-0083).
export interface ReconnectDiagnosisDesk {
  outcome: string;
  title: string;
  advice: string;
  evidence: string[];
}
export interface ReconnectDeviceDesk {
  adapter: string;
  adapterName: string;
  mac: string;
  name: string;
  class: string | null;
  modalias: string | null;
  transport: "bredr" | "le" | "unknown";
  connected: boolean;
  unregisteredPrefix: boolean;
  help: boolean;
  commit: boolean;
  last: ReconnectDiagnosisDesk | null;
  suggest: { reason: string } | null;
  captured: boolean;
  stored?: { linkKey: boolean; keyType: number | null; trusted: boolean; services: boolean; backups: number } | null;
}
export interface ReconnectDesk {
  available: boolean;
  problem: string | null;
  off?: boolean;
  helper?: { installed: boolean; ready: boolean; problem?: string; version?: string };
  sspGate?: { on: boolean; adapter: string | null; state: string };
  adapters?: { address: string; name: string }[];
  devices?: ReconnectDeviceDesk[];
  dryRun?: boolean;
  cableReady?: boolean;
  actions?: { at: string; action: string; device: string | null }[];
}
export interface ControllerSettingsDesk {
  off?: boolean;
  problem: string | null;
  present?: boolean;
  current?: Record<string, string> | null;
  kept: Record<string, unknown>;
  allowed: string[];
  tools: { hhd?: boolean; inputplumber?: boolean };
  helper: { ready?: boolean };
}
export interface ExtrasDesk {
  wifiPowerSaving: boolean | null;
  bios: { version: string | null; known?: boolean; notes: string[]; level: string };
}
