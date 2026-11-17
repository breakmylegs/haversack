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
