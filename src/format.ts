// Small display helpers shared by the pages. Timestamps are shown, never used to decide (principle 4).
import { HealthStatus, PlanEntry, SyncWord } from "./backend";

export function sizeText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function isoText(iso: string | null | undefined): string {
  return iso ? iso.replace("T", " ").replace("Z", "") : "unknown time";
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

export const CONFLICT_TEXT = {
  adoption: "This device has save files that differ from the cloud, and they have never been synced.",
  fork: "Two devices saved different progress from the same starting point.",
  "both-changed": "This device and the cloud both have new progress.",
};
