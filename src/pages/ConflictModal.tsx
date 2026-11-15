import { DialogButton, Focusable, ModalRoot, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { ConflictDetails, ConflictSide, conflictDetails, resolveConflict } from "../backend";
import { CONFLICT_TEXT, isoText, sizeText } from "../format";

// Build prompt section 14: initial focus on "Decide later", B means "Decide later", and the
// choices that replace files need a second, explicit press. Closing the modal any other way
// is also "Decide later", so it can never be dismissed into data loss.

export function openConflictModal(gameKey: string, onDone: () => void) {
  showModal(<ConflictModal gameKey={gameKey} onDone={onDone} />);
}

function sideText(side: ConflictSide, hasBase: boolean): string {
  const changed = hasBase ? `${side.changedFiles} changed since the last sync` : "never synced together";
  const when = side.side === "local" ? "now" : isoText(side.created);
  return `${when}, ${side.files} files, ${sizeText(side.bytes)}, ${changed}`;
}

function ConflictModal({ gameKey, onDone, closeModal }: { gameKey: string; onDone: () => void; closeModal?: () => void }) {
  const [details, setDetails] = useState<ConflictDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [armed, setArmed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    conflictDetails(gameKey)
      .then(setDetails)
      .catch((err) => setError(String(err)));
  }, [gameKey]);

  const decideLater = () => {
    closeModal?.();
    onDone();
  };

  const choose = async (choice: "use-cloud" | "use-local", head: string | null) => {
    const id = choice === "use-local" ? choice : `cloud:${head}`;
    if (armed !== id) {
      setArmed(id); // first press only arms the choice
      return;
    }
    setBusy(true);
    try {
      await resolveConflict(gameKey, choice, head);
      toaster.toast({ title: "Keepsake", body: "Conflict resolved. The save you did not choose is kept and pinned." });
      closeModal?.();
      onDone();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Not resolved: ${err}` });
      setArmed(null);
      setBusy(false);
    }
  };

  const sides = details?.sides ?? [];
  const hasBase = Boolean(details?.hasBase);
  const local = sides.find((s) => s.side === "local");

  return (
    <ModalRoot onCancel={decideLater} closeModal={closeModal} bCancelDisabled={busy}>
      <div style={{ fontSize: 20, fontWeight: "bold", marginBottom: 8 }}>Save conflict{details ? `: ${details.name}` : ""}</div>
      {error && <div>Could not load the conflict: {error}. Choose Decide later and try again when online.</div>}
      {!details && !error && <div>Loading both sides of the conflict.</div>}
      {details && !details.conflict && <div>This conflict has already been resolved.</div>}
      {details?.conflict && (
        <>
          <div style={{ marginBottom: 8 }}>
            {CONFLICT_TEXT[details.conflict.kind]} Whichever you do not choose is kept and pinned for at least 90 days.
            Quit the game before choosing.
          </div>
          {local && (
            <div style={{ marginBottom: 4 }}>
              <b>This device:</b> {sideText(local, hasBase)}
            </div>
          )}
          {sides
            .filter((s) => s.side === "cloud")
            .map((s) => (
              <div key={s.snapId} style={{ marginBottom: 4 }}>
                <b>Cloud, from {s.device ?? "an unknown device"}:</b> {sideText(s, hasBase)}
              </div>
            ))}
        </>
      )}
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
        <DialogButton style={{ width: "auto" }} preferredFocus onClick={decideLater}>
          Decide later
        </DialogButton>
        {details?.conflict &&
          sides
            .filter((s) => s.side === "cloud")
            .map((s) => (
              <DialogButton
                key={s.snapId}
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() => void choose("use-cloud", s.snapId)}
              >
                {armed === `cloud:${s.snapId}`
                  ? "Press again to use this cloud save"
                  : `Use cloud save from ${s.device ?? "the cloud"}`}
              </DialogButton>
            ))}
        {details?.conflict && (
          <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void choose("use-local", null)}>
            {armed === "use-local" ? "Press again to use this device's save" : "Use this device's save"}
          </DialogButton>
        )}
      </Focusable>
    </ModalRoot>
  );
}
