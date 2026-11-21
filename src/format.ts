// Small display helpers shared by the pages. Timestamps are shown, never used to decide (principle 4).
import { Backend, HealthStatus, PlanEntry, SyncWord } from "./backend";

export const BACKEND_LABELS: Record<Backend, string> = {
  local: "Test store",
  onedrive: "OneDrive",
  gdrive: "Google Drive",
  webdav: "WebDAV",
  s3: "S3",
  direct: "Directly between my devices",
};

export function sizeText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function isoText(iso: string | null | undefined): string {
  return iso ? iso.replace("T", " ").replace("Z", "") : "unknown time";
}

/** "Newer save from <device>, 10 minutes ago" (ADR-0049). */
export function newerText(newer: { device: string | null; created: string | null }): string {
  const when = newer.created ? agoText(Date.parse(newer.created) / 1000) : "";
  return `Newer save from ${newer.device ?? "another device"}${when ? `, ${when}` : ""}`;
}

export function agoText(seconds: number | null | undefined, now: number = Date.now() / 1000): string {
  if (!seconds) return "never";
  const age = Math.max(0, now - seconds);
  if (age < 90) return "just now";
  if (age < 3600) return `${Math.round(age / 60)} minutes ago`;
  if (age < 48 * 3600) return `${Math.round(age / 3600)} hours ago`;
  return `${Math.round(age / 86400)} days ago`;
}

export const SYNC_LABELS: Record<SyncWord, string> = {
  off: "Not synced by Keepsake",
  "not-synced": "Not synced yet",
  synced: "Synced",
  pending: "Waiting for the cloud",
  conflict: "Conflict: your choice needed",
  quarantined: "Suspicious save kept on this device",
};

export const HEALTH_LABELS: Record<HealthStatus, string> = {
  ok: "All good",
  info: "All good",
  warn: "Needs attention",
  fail: "Problem",
};

export const HEALTH_COLOURS: Record<HealthStatus, string> = {
  ok: "#59bf40",
  info: "#59bf40",
  warn: "#e5b33a",
  fail: "#e04f4f",
};

export const PLAN_LABELS: Record<PlanEntry["action"], string> = {
  push: "Upload this device's saves",
  pull: "Download the cloud save",
  adopt: "Already the same as the cloud",
  conflict: "Conflict: you will choose which save to keep",
  "up-to-date": "Up to date",
  nothing: "No saves on this device or in the cloud yet",
  offline: "Cloud not reachable: checked at the next sync",
  error: "Cannot sync yet",
};

const KIND_LABELS: Record<string, string> = {
  provisional: "sleep snapshot (never used automatically)",
  import: "Ludusavi import",
  "auto-exit": "after play",
  "auto-recovered": "recovered",
  merge: "conflict resolved",
};

export function kindText(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

export const CONFLICT_TEXT = {
  adoption: "This device has save files that differ from the cloud, and they have never been synced.",
  fork: "Two devices saved different progress from the same starting point.",
  "both-changed": "This device and the cloud both have new progress.",
};

/**
 * A backend error as a plain sentence (v0.30.2). Decky raises a Python error as "Python ValueError:
 * <message>"; Keepsake's ValueErrors are already plain, so only the message is shown. Anything
 * else is a fault, named once with a pointer to diagnostics, never a raw exception.
 */
export function plainError(err: unknown): string {
  if (err instanceof Error && err.name.startsWith("Python ")) {
    if (err.name === "Python ValueError" && err.message) return sentence(err.message);
    return `Something went wrong in Keepsake (${err.name.slice(7)}). If it keeps happening, export diagnostics from Settings.`;
  }
  const text = err instanceof Error ? err.message : String(err);
  return sentence(text.replace(/^(Python )?[A-Za-z]*Error: /, ""));
}

function sentence(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return "That did not work.";
  const first = trimmed[0].toUpperCase() + trimmed.slice(1);
  return /[.!?]$/.test(first) ? first : `${first}.`;
}
