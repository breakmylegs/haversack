import { ConfirmModal, DialogButton, Field, Focusable, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { PairedDevice, replicationSend, replicationStatus } from "../backend";
import { plainError } from "../format";

// "Send to <device>" on a non-Steam game's page (ADR-0059). Shown only while Replication runs.
export function SendPanel({ gameKey, gameName }: { gameKey: string; gameName: string }) {
  const [peers, setPeers] = useState<PairedDevice[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    replicationStatus()
      .then((s) => setPeers(s.peers))
      .catch(() => undefined); // Replication is off (no panel), or busy: keep what is shown
  }, []);

  if (!peers) return null;
  if (peers.length === 0) {
    return <Field label="Send to another device" description="Pair a device in Other devices first." />;
  }

  const send = (peer: PairedDevice) =>
    showModal(
      <ConfirmModal
        strTitle={`Send ${gameName} to ${peer.name}?`}
        strDescription={
          "Haversack checks that device has space, then copies the game, its Proton prefix, its compatibility tool " +
          "and its artwork there, and adds it to Steam. The game's saves go with this first copy; later updates never " +
          "replace them. It starts by itself; either device can stop and remove it."
        }
        strOKButtonText="Send"
        strCancelButtonText="Cancel"
        onOK={async () => {
          setBusy(true);
          try {
            const result = await replicationSend(gameKey, peer.id);
            const dropped = result.droppedOptions.length
              ? ` These launch options stay on this device: ${result.droppedOptions.join(" ")}.`
              : "";
            toaster.toast({ title: "Haversack", body: `Preparing ${result.title} for ${peer.name}.${dropped}` });
          } catch (err) {
            toaster.toast({ title: "Haversack", body: plainError(err) });
          } finally {
            setBusy(false);
          }
        }}
      />,
    );

  return (
    <Field
      label="Send to another device"
      description="Copies this game straight to a paired device, never through the cloud."
      childrenLayout="below"
    >
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {peers.map((peer) => (
          <DialogButton key={peer.id} style={{ width: "auto" }} disabled={busy} onClick={() => send(peer)}>
            Send to {peer.name}
          </DialogButton>
        ))}
      </Focusable>
    </Field>
  );
}
