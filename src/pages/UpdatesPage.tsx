import { DialogButton, Field, Focusable } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { checkForUpdates, prepareUpdate, ReleaseInfo, UpdateStatus } from "../backend";
import { handOff, handOffAvailable, reasonText, RELEASES_PAGE } from "../update";
import { QrCode } from "./QrCode";

const IDLE_EVENT = "keepsake_idle";

interface Fallback {
  version: string;
  url: string;
}

function formatDate(iso: string): string {
  return iso ? iso.slice(0, 10) : "";
}

function NotesBlock({ notes }: { notes: string }) {
  return (
    <Focusable
      style={{ background: "rgba(0, 0, 0, 0.3)", borderRadius: 4, padding: 8, maxHeight: 240, overflowY: "auto" }}
    >
      <pre style={{ margin: 0, fontSize: 12, whiteSpace: "pre-wrap" }}>{notes || "No release notes."}</pre>
    </Focusable>
  );
}

export function UpdatesPage() {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [notesFor, setNotesFor] = useState<string | null>(null);
  const [waitingTag, setWaitingTag] = useState<string | null>(null);
  const [fallback, setFallback] = useState<Fallback | null>(null);
  const idleListener = useRef<((...args: unknown[]) => unknown) | null>(null);

  const refresh = async (force: boolean) => {
    setChecking(true);
    try {
      setStatus(await checkForUpdates(force));
    } catch (err) {
      setMessage(`Could not check for updates: ${err}`);
    } finally {
      setChecking(false);
    }
  };

  const stopWaiting = () => {
    if (idleListener.current) removeEventListener(IDLE_EVENT, idleListener.current);
    idleListener.current = null;
    setWaitingTag(null);
  };

  useEffect(() => {
    void refresh(false);
    return stopWaiting;
  }, []);

  const install = async (release: ReleaseInfo) => {
    setMessage(null);
    setFallback(null);
    const prepared = await prepareUpdate(release.tag);
    if (!prepared.ok) {
      setMessage(reasonText(prepared.reason));
      if (prepared.reason === "busy") setWaitingTag(release.tag);
      return;
    }
    if (!handOffAvailable()) {
      setFallback({ version: prepared.displayVersion, url: prepared.artifact });
      return;
    }
    await handOff(prepared);
    setMessage(`Decky Loader will ask you to confirm installing v${prepared.displayVersion}.`);
  };

  const updateWhenIdle = (release: ReleaseInfo) => {
    stopWaiting();
    const listener = () => {
      stopWaiting();
      toaster.toast({ title: "Haversack", body: "Sync finished. Preparing the update." });
      void install(release);
    };
    idleListener.current = addEventListener(IDLE_EVENT, listener);
    setWaitingTag(release.tag);
    setMessage("Haversack will offer the update when the current sync finishes.");
  };

  const latest = status?.latest ?? null;
  const waitingRelease = status?.releases.find((r) => r.tag === waitingTag) ?? null;

  return (
    <div>
      <Field
        label={`Installed version ${status?.current ?? ""}`}
        description={`Channel: ${status?.channel === "prerelease" ? "Pre-release" : "Stable"}. Change it in Settings.`}
      />
      <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
        <DialogButton style={{ width: "auto" }} disabled={checking} onClick={() => void refresh(true)}>
          {checking ? "Checking" : "Check for updates"}
        </DialogButton>
      </Focusable>
      {status?.error && (
        <Field label="Last check did not complete" description={`Reason: ${status.error}. Showing cached releases.`} />
      )}
      {message && <Field label={message} />}
      {waitingRelease && !idleListener.current && (
        <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
          <DialogButton style={{ width: "auto" }} onClick={() => updateWhenIdle(waitingRelease)}>
            Update when idle
          </DialogButton>
        </Focusable>
      )}
      {fallback && (
        <Field
          label={`Install v${fallback.version} from URL`}
          description="This Decky Loader version does not let plugins start an install. In Decky, open Settings, Developer, Install plugin from URL, and enter this address, or scan the code with your phone to copy it."
          childrenLayout="below"
        >
          <div style={{ fontSize: 12, wordBreak: "break-all", margin: "8px 0" }}>{fallback.url}</div>
          <QrCode text={fallback.url} />
        </Field>
      )}

      {latest && status?.updateAvailable && (
        <Field label={`Update available: v${latest.version}`} childrenLayout="below">
          <NotesBlock notes={latest.notes} />
          <Focusable style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <DialogButton style={{ width: "auto" }} onClick={() => void install(latest)}>
              Update now
            </DialogButton>
          </Focusable>
        </Field>
      )}
      {status && !status.updateAvailable && <Field label="Haversack is up to date." />}

      <Field label="All releases" description={`Install any release to roll back. Releases page: ${RELEASES_PAGE}`} />
      {(status?.releases ?? []).map((release) => {
        const current = release.version === status?.current;
        return (
          <Field
            key={release.tag}
            label={`v${release.version}${release.prerelease ? "  (pre-release)" : ""}${current ? "  (installed)" : ""}`}
            description={`${formatDate(release.published)}${release.complete ? "" : "  Missing zip or SHA256SUMS"}`}
            childrenLayout="below"
          >
            <Focusable style={{ display: "flex", gap: 8 }}>
              <DialogButton
                style={{ width: "auto" }}
                onClick={() => setNotesFor(notesFor === release.tag ? null : release.tag)}
              >
                {notesFor === release.tag ? "Hide notes" : "Release notes"}
              </DialogButton>
              <DialogButton
                style={{ width: "auto" }}
                disabled={current || !release.complete}
                onClick={() => void install(release)}
              >
                Install this version
              </DialogButton>
            </Focusable>
            {notesFor === release.tag && <NotesBlock notes={release.notes} />}
          </Field>
        );
      })}
    </div>
  );
}
