// Small display helpers shared by the pages.
import { HealthStatus } from "./backend";

export function sizeText(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function agoText(seconds: number | null | undefined, now: number = Date.now() / 1000): string {
  if (!seconds) return "never";
  const age = Math.max(0, now - seconds);
  if (age < 90) return "just now";
  if (age < 3600) return `${Math.round(age / 60)} minutes ago`;
  if (age < 48 * 3600) return `${Math.round(age / 3600)} hours ago`;
  return `${Math.round(age / 86400)} days ago`;
}

export const HEALTH_LABELS: Record<HealthStatus, string> = {
  ok: "All good",
  info: "All good",
  warn: "Needs attention",
  fail: "Problem",
};

// Status colours from the Okabe-Ito palette, which stays distinct for the common kinds of colour
// blindness (v0.50.0). Green and red alone are not: every status also has its own icon shape or words.
export const STATUS = {
  ok: "#009E73", // bluish green
  warn: "#E69F00", // orange
  fail: "#D55E00", // vermilion
  info: "#56B4E9", // sky blue
  neutral: "#8a8fa3",
} as const;

/**
 * A backend error as a plain sentence (v0.30.2). Decky raises a Python error as "Python ValueError:
 * <message>"; Haversack's ValueErrors are already plain, so only the message is shown. Anything
 * else is a fault, named once with a pointer to diagnostics, never a raw exception.
 */
export function plainError(err: unknown): string {
  if (err instanceof Error && err.name.startsWith("Python ")) {
    if (err.name === "Python ValueError" && err.message) return sentence(err.message);
    return `Something went wrong in Haversack (${err.name.slice(7)}). If it keeps happening, export diagnostics from Diagnostics, Tools.`;
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
