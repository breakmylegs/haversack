import { DialogButton, DropdownItem, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { GameLink, replicationCheckGame, replicationGames, replicationSendUpdate, replicationSetPolicy } from "../backend";
import { plainError } from "../format";

const STATE_TEXT: Record<GameLink["state"], string> = {
  "in-sync": "In step with the other device.",
  "changed-here": "Changed on this device since the last sync.",
  "update-available": "An update from the other device is waiting in Devices.",
  "both-changed": "Changed on both devices: choose which copy to keep in Devices.",
  updating: "Taking the update from the other device.",
};

// Keeping a game you sent or received in step with the other device (ADR-0060).
export function InStepPanel({ appid }: { appid: number }) {
  const [link, setLink] = useState<GameLink | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    replicationGames()
      .then((links) => setLink(links.find((l) => l.appid === appid) ?? null))
      .catch(() => setLink(null)); // Replication is off
  useEffect(() => void load(), [appid]);

  if (!link) return null;
  const run = async (work: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      await work();
      if (done) toaster.toast({ title: "Keepsake", body: done });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(false);
      await load();
    }
  };

  return (
    <>
      <Field label="Kept in step with the other device" description={STATE_TEXT[link.state]} />
      <DropdownItem
        label="Updates"
        description="Your saves and settings on each device are never replaced by an update."
        rgOptions={[
          { data: "manual", label: "Ask me (Manual)" },
          { data: "auto", label: "Take them by themselves (Auto)" },
          { data: "off", label: "Off" },
        ]}
        selectedOption={link.policy}
        disabled={busy}
        onChange={(option) => void run(() => replicationSetPolicy(link.id, option.data))}
      />
      <Field childrenLayout="below">
        <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() => void run(() => replicationCheckGame(link.id), "Checked. A big game takes a while.")}
          >
            Check now
          </DialogButton>
          {link.state === "changed-here" && (
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy}
              onClick={() => void run(() => replicationSendUpdate(link.id), "The update is offered to the other device.")}
            >
              Send update
            </DialogButton>
          )}
        </Focusable>
      </Field>
    </>
  );
}
