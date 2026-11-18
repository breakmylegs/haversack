import { ConfirmModal, DialogButton, DropdownItem, Field, Focusable, TextField, ToggleField, showModal } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  FoundDevice,
  Pairing,
  PairedDevice,
  ReplicationStatus,
  replicationAnswer,
  replicationCancel,
  replicationCheck,
  replicationClosePairing,
  replicationFind,
  replicationOpenPairing,
  replicationPair,
  replicationRemove,
  replicationSetAddress,
  replicationSetListener,
  replicationStatus,
  replicationWake,
} from "../backend";

const REPLICATION_EVENT = "keepsake_replication";

function seen(seconds: number): string {
  return seconds ? new Date(seconds * 1000).toLocaleString() : "never";
}

function active(p: Pairing): boolean {
  return p.state === "connecting" || p.state === "compare" || p.state === "waiting";
}

// Paired devices, pairing by a confirmed code, and the listener (ADR-0054, ADR-0056).
export function ReplicationPage() {
  const [status, setStatus] = useState<ReplicationStatus | null>(null);
  const [found, setFound] = useState<FoundDevice[] | null>(null);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    replicationStatus()
      .then(setStatus)
      .catch((err) => toaster.toast({ title: "Keepsake", body: String(err) }));

  useEffect(() => {
    void refresh();
    const listener = addEventListener(REPLICATION_EVENT, () => void refresh());
    return () => removeEventListener(REPLICATION_EVENT, listener);
  }, []);

  // While a pairing runs or the window is open, follow it every second.
  const following = !!status && (status.listener.pairingOpen || status.pairings.some(active));
  useEffect(() => {
    if (!following) return;
    const timer = setInterval(() => void refresh(), 1000);
    return () => clearInterval(timer);
  }, [following]);

  const run = async (work: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      const result = await work();
      if (result && typeof result === "object" && "listener" in result) setStatus(result as ReplicationStatus);
      else await refresh();
      if (done) toaster.toast({ title: "Keepsake", body: done });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
    }
  };

  if (!status) return <Field label="Devices" description="Loading" />;
  if (!status.available) {
    return (
      <Field
        label="Devices"
        description="This device's Python cannot make Replication's encrypted link, so Replication stays off. See Settings, Health."
      />
    );
  }
  const listener = status.listener;
  const pairings = status.pairings.filter((p) => active(p) || p.state === "failed");

  return (
    <div>
      <Field
        label="Your devices"
        description="Keepsake links your own devices directly, on your home network or your own VPN. Nothing goes through the cloud. Pair each device once by checking that both screens show the same code."
      />

      {pairings.map((p) => (
        <PairingCard key={p.id} pairing={p} busy={busy} run={run} />
      ))}

      <ToggleField
        label="Let other devices reach this one"
        description={
          listener.on
            ? `Listening on ${listener.addresses.join(", ") || "no address"}, port ${listener.port}. Only paired devices get in.`
            : "Off: no other device can connect to this one. Switch it on to pair or to receive games."
        }
        checked={listener.on}
        disabled={busy}
        onChange={(on) => void run(() => replicationSetListener(on))}
      />
      {status.discovery.problem && <Field description={status.discovery.problem} />}
      {status.addressesAvailable.length > 1 && (
        <DropdownItem
          label="Listen on"
          description="Every home network and VPN address, or only one of them."
          rgOptions={[
            { data: "", label: "All home network and VPN addresses" },
            ...status.addressesAvailable.map((a) => ({
              data: a.address,
              label: `${a.address}${a.kind === "overlay" ? " (VPN)" : ""}`,
            })),
          ]}
          selectedOption={status.addressChoice}
          disabled={busy}
          onChange={(option) => void run(() => replicationSetAddress(option.data))}
        />
      )}

      <Field label="Pair a device" childrenLayout="below">
        <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {listener.pairingOpen ? (
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run(replicationClosePairing)}>
              Stop accepting ({listener.pairingSecondsLeft} s)
            </DialogButton>
          ) : (
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy || !listener.on}
              onClick={() => void run(replicationOpenPairing, "Open Keepsake on the other device and pair with this one.")}
            >
              Let a device pair with this one
            </DialogButton>
          )}
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() => void run(async () => setFound(await replicationFind()))}
          >
            Find devices
          </DialogButton>
        </Focusable>
      </Field>
      {found && found.length === 0 && (
        <Field description="No devices answered. On the other device, switch on Let other devices reach this one, or type its address below." />
      )}
      {(found ?? []).map((d) => (
        <Field key={d.id} label={d.name} description={`${d.address}${d.paired ? ", already paired" : ""}`} childrenLayout="below">
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() => void run(() => replicationPair(`${d.address.includes(":") ? `[${d.address}]` : d.address}:${d.port}`))}
          >
            Pair
          </DialogButton>
        </Field>
      ))}
      <Field
        label="Pair by address"
        description="For a device on your VPN, or one not found above: its address, such as 192.168.1.20 or 100.101.102.103."
        childrenLayout="below"
      >
        <TextField value={address} disabled={busy} onChange={(e) => setAddress(e.target.value)} />
        <DialogButton
          style={{ width: "auto", marginTop: 8 }}
          disabled={busy || !address.trim()}
          onClick={() => void run(() => replicationPair(address.trim()))}
        >
          Pair
        </DialogButton>
      </Field>

      <Field label="Paired devices" description={status.peers.length ? undefined : "None yet."} />
      {status.peers.map((peer) => (
        <PeerRow key={peer.id} peer={peer} busy={busy} run={run} />
      ))}
    </div>
  );
}

function PairingCard(props: { pairing: Pairing; busy: boolean; run: (work: () => Promise<unknown>, done?: string) => Promise<void> }) {
  const { pairing: p, busy, run } = props;
  const who = p.peerName ?? p.address;
  if (p.state === "failed") return <Field label={`Pairing with ${who} did not finish`} description={p.reason ?? ""} />;
  if (p.state === "connecting") {
    return (
      <Field label={`Connecting to ${who}`} childrenLayout="below">
        <DialogButton style={{ width: "auto" }} onClick={() => void run(() => replicationCancel(p.id))}>
          Cancel
        </DialogButton>
      </Field>
    );
  }
  if (p.state === "waiting") return <Field label={`Code ${p.code}`} description={`Waiting for ${who} to confirm.`} />;
  return (
    <Field
      label={`Pair with ${who}? Code ${p.code}`}
      description="Check that the other device shows exactly the same code. If it differs, say so: someone else may be on the network."
      childrenLayout="below"
    >
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run(() => replicationAnswer(p.id, true))}>
          The codes match
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run(() => replicationAnswer(p.id, false))}>
          They differ
        </DialogButton>
      </Focusable>
    </Field>
  );
}

function PeerRow(props: { peer: PairedDevice; busy: boolean; run: (work: () => Promise<unknown>, done?: string) => Promise<void> }) {
  const { peer, busy, run } = props;
  const [result, setResult] = useState<string | null>(null);
  const check = async () => {
    const r = await replicationCheck(peer.id);
    if (!r.ok) setResult(r.reason ?? "Not reachable.");
    else {
      const note = r.slow ? (r.overlay ? " Slow: your VPN may be relaying this link." : " Slow.") : "";
      setResult(`Reachable at ${r.address}, ${r.rttMs} ms.${note}`);
    }
  };
  return (
    <Field
      label={peer.name}
      description={`${result ?? `Last seen ${seen(peer.lastSeen)}`}${peer.address ? ` at ${peer.address}` : ""}`}
      childrenLayout="below"
    >
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run(check)}>
          Check
        </DialogButton>
        {peer.canWake && (
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() => void run(() => replicationWake(peer.id), "Wake signal sent. A device asleep on Wi-Fi may not wake.")}
          >
            Wake
          </DialogButton>
        )}
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() =>
            showModal(
              <ConfirmModal
                strTitle={`Remove ${peer.name}?`}
                strDescription="Its link key is deleted on this device, and it can no longer connect. Pair again to link it back."
                strOKButtonText="Remove"
                strCancelButtonText="Cancel"
                onOK={() => void run(() => replicationRemove(peer.id), "Device removed.")}
              />,
            )
          }
        >
          Remove
        </DialogButton>
      </Focusable>
    </Field>
  );
}
