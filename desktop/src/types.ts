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
  state: "connecting" | "compare" | "waiting" | "paired" | "failed" | "cancelled";
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
  listener: { on: boolean; addresses: string[]; port: number; pairingOpen: boolean; pairingSecondsLeft: number };
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
