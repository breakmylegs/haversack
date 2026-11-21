// Games you can stream from another device: Steam Remote Play's entries (ADR-0064). Shows how many there
// are and the guard's Show it again. The tidy-up (hide the ticked ones through Steam, with Undo) only appears
// once a device run shows hiding one leaves the real game on the other device visible (A201).
import { DialogButton, Field, Focusable, ModalRoot, ToggleField, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { RemoteCopiesStatus, remoteCopiesStatus, setSetting, tidyCopies, undoTidy, unhideLocal } from "../backend";
import { reportRemoteCopies } from "../remotecopies";

function TidyModal({ status, closeModal, onDone }: { status: RemoteCopiesStatus; closeModal?: () => void; onDone: () => void }) {
  const certain = status.copies.filter((c) => c.presence === "remote" && !c.hidden);
  const unsure = status.copies.filter((c) => c.presence === "unsure");
  const [ticked, setTicked] = useState<Set<number>>(new Set(certain.map((c) => c.appid)));
  const [busy, setBusy] = useState(false);
  const toggle = (appid: number, on: boolean) => {
    const next = new Set(ticked);
    if (on) next.add(appid);
    else next.delete(appid);
    setTicked(next);
  };
  const hide = async () => {
    setBusy(true);
    try {
      const r = await tidyCopies([...ticked]);
      toaster.toast({ title: "Keepsake", body: `Hiding ${r.queued} games in Steam. Undo tidy-up shows them again.` });
      onDone();
      closeModal?.();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <Field
        label="Tidy up games you can stream from another device"
        description="Steam Remote Play lists the games on your other devices here, with Stream instead of Play. Hiding them puts them in Steam's Hidden collection; nothing is deleted. Steam may share hidden games across your devices: if a game on another device is hidden by this, Keepsake there offers to show it again."
      />
      {certain.length === 0 && <Field label="Nothing to hide" />}
      {certain.map((c) => (
        <ToggleField
          key={c.appid}
          label={c.name || `App ${c.appid}`}
          description={[c.from.length ? `from ${c.from.join(", ")}` : "from another device", c.clash ? "same name as a game on this device" : ""]
            .filter(Boolean)
            .join(", ")}
          checked={ticked.has(c.appid)}
          onChange={(on) => toggle(c.appid, on)}
        />
      ))}
      {unsure.length > 0 && (
        <Field
          label={`${unsure.length} not sure, left alone`}
          description={unsure.map((c) => c.name).join(", ")}
        />
      )}
      <Focusable style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <DialogButton style={{ width: "auto" }} onClick={closeModal}>
          Cancel
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={busy || ticked.size === 0} onClick={() => void hide()}>
          {`Hide ${ticked.size}`}
        </DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

/** The tidy-up controls: a summary, Tidy up, Undo, the automatic option, and the guard's Show again. */
export function TidyCopies({ onChange }: { onChange?: () => void }) {
  const [status, setStatus] = useState<RemoteCopiesStatus | null>(null);
  const [show, setShow] = useState(false);
  const refresh = async () => {
    try {
      await reportRemoteCopies();
      setStatus(await remoteCopiesStatus());
    } catch {
      setStatus(null); // Saves off or the backend not ready: nothing to show
    }
  };
  useEffect(() => {
    void refresh();
  }, []);
  if (!status) return null;
  const done = () => {
    void refresh();
    onChange?.();
  };
  const certain = status.copies.filter((c) => c.presence === "remote");
  const hidden = Object.values(status.log).filter((e) => e.state === "hidden" || e.state === "pending").length;
  const canUndo = Object.values(status.log).some((e) => ["pending", "hidden", "came-back"].includes(e.state));
  return (
    <>
      {status.newlyHidden.map((g) => (
        <Field
          key={g.appid}
          label={`${g.name} is hidden in Steam`}
          description="It is a game on this device. It may have been hidden from your other device."
          childrenLayout="inline"
        >
          <DialogButton
            style={{ width: "auto" }}
            onClick={() =>
              void unhideLocal(g.appid)
                .then(() => toaster.toast({ title: "Keepsake", body: `${g.name} shows again in your library.` }))
                .then(done)
            }
          >
            Show it again
          </DialogButton>
        </Field>
      ))}
      <Field
        label="Games you can stream from another device"
        description={
          status.reportAt === null
            ? "Steam has not reported its library yet."
            : `${certain.length} games in your library are installed on another device and offer Stream (Steam Remote Play)${hidden ? `, ${hidden} hidden by a tidy-up` : ""}. Keepsake never treats them as games on this device. To see only what is installed here, use Steam's Installed tab, or switch off Remote Play in Steam's settings.`
        }
        childrenLayout="inline"
      >
        <Focusable style={{ display: "flex", gap: 8 }}>
          {status.tidyAvailable && (
            <DialogButton
              style={{ width: "auto" }}
              disabled={!status.copies.length}
              onClick={() => showModal(<TidyModal status={status} onDone={done} />)}
            >
              Tidy up
            </DialogButton>
          )}
          {canUndo && (
            <DialogButton
              style={{ width: "auto" }}
              onClick={() =>
                void undoTidy()
                  .then((r) => toaster.toast({ title: "Keepsake", body: `Showing ${r.queued} games again.` }))
                  .then(done)
              }
            >
              Undo tidy-up
            </DialogButton>
          )}
        </Focusable>
      </Field>
      <ToggleField
        label="Show games you can stream from another device"
        description="Lists them here. Keepsake leaves them out of the Games list, save sync, Send to, Replication and Advisor."
        checked={show}
        onChange={setShow}
      />
      {show &&
        status.copies.map((c) => (
          <Field
            key={c.appid}
            label={c.name || `App ${c.appid}`}
            description={[
              c.presence === "remote" ? `stream from ${c.from.join(", ") || "another device"}` : "Steam is not sure where this one is installed",
              c.clash ? "also installed here" : "",
              c.hidden ? "hidden" : "",
            ]
              .filter(Boolean)
              .join(", ")}
          />
        ))}
      {status.tidyAvailable && (
        <ToggleField
          label="Tidy up automatically when new ones appear"
          description="Hides new games you can stream from another device as Steam shows them. Only ever ones Steam says are on another device; one you show again stays shown."
          checked={status.automatic}
          onChange={(on) => void setSetting("tidyAutomatically", on).then(done)}
        />
      )}
    </>
  );
}
