// Hand-off to Decky Loader's own installer (ADR-0002).
//
// Decky's websocket route "utilities/install_plugin" only requests an install:
// Decky shows its own confirmation, downloads the zip, refuses it if the
// SHA-256 does not match, and replaces and reloads the plugin. This is the
// same route as Decky's "Install plugin from URL". It is not part of the typed
// @decky/api surface, so it is feature-detected and there is a fallback.
import { PreparedUpdate } from "./backend";

interface DeckyBackendLike {
  call?: (route: string, ...args: unknown[]) => Promise<unknown>;
}

export const RELEASES_PAGE = "https://github.com/breakmylegs/haversack/releases";

export function handOffAvailable(): boolean {
  const backend = (window as unknown as { DeckyBackend?: DeckyBackendLike }).DeckyBackend;
  return typeof backend?.call === "function";
}

export async function handOff(prepared: Extract<PreparedUpdate, { ok: true }>): Promise<boolean> {
  const backend = (window as unknown as { DeckyBackend?: DeckyBackendLike }).DeckyBackend;
  if (typeof backend?.call !== "function") return false;
  await backend.call(
    "utilities/install_plugin",
    prepared.artifact,
    prepared.name,
    prepared.version,
    prepared.sha256,
    prepared.installType,
  );
  return true;
}

const REASONS: Record<string, string> = {
  busy: "Update after the current sync.",
  "unknown-release": "That release was not found. Check for updates and try again.",
  "incomplete-release": "That release is missing its zip or SHA256SUMS file, so it cannot be verified.",
  "disallowed-host": "That release points at a download address Haversack does not trust.",
  offline: "GitHub could not be reached. Try again when online.",
  "sums-unavailable": "The release's SHA256SUMS file could not be downloaded.",
  "sums-missing-zip": "SHA256SUMS does not list the release zip, so it cannot be verified.",
  "unsigned-release": "That release is not signed, so Haversack will not install it.",
  "signature-unavailable": "The release's signature could not be downloaded. Try again later.",
  "bad-signature": "The release's signature is not valid for Haversack's release key, so it was not installed.",
};

export function reasonText(reason: string): string {
  return REASONS[reason] ?? `Update refused (${reason}).`;
}
