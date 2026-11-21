import { ConfirmModal, DialogButton, DropdownItem, Field, Focusable, TextField, ToggleField, showModal } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  FoundDevice,
  Pairing,
  PairedDevice,
  ReplicationStatus,
  replicationAnswer,
  replicationEnterCode,
  replicationCancel,
  replicationCheck,
  replicationFind,
  replicationPair,
  replicationRemove,
  replicationSetAddress,
  replicationSetListener,
  replicationStatus,
  replicationWake,
  replicationPause,
  replicationResume,
  replicationStop,
  replicationTransfers,
  TransferJob,
  TransfersStatus,
  IncomingOffer,
  OffersStatus,
  replicationAccept,
  replicationDecline,
  replicationDismiss,
  replicationOfferCheck,
  replicationOffers,
  replicationRemoveGame,
  replicationWithdraw,
  replicationApplyUpdate,
  replicationKeepMine,
} from "../backend";

const REPLICATION_EVENT = "keepsake_replication";

function seen(seconds: number): string {
  return seconds ? new Date(seconds * 1000).toLocaleString() : "never";
}

const ACTIVE = ["connecting", "waiting-accept", "enter-code", "request", "show-code", "checking"];

function active(p: Pairing): boolean {
  return ACTIVE.includes(p.state);
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

  // While a pairing runs, follow it every second.
  const following = !!status && status.pairings.some(active);
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
  const pairings = status.pairings.filter((p) => active(p) || p.state === "failed" || p.state === "declined");

  return (
    <div>
      <Field
        label="Your devices"
        description="Keepsake links your own devices directly, on your home network or your own VPN. Nothing goes through the cloud. Pair each device once: send a request from one, accept it on the other, and type the code it shows."
      />

      <OffersSection />
      <TransfersSection />

      {pairings.map((p) => (
        <PairingCard key={p.id} pairing={p} busy={busy} run={run} />
      ))}

      <ToggleField
        label="Let other devices reach this one"
        description={
          listener.on
            ? `Listening on ${listener.addresses.join(", ") || "no address"}, port ${listener.port}. Only paired devices get in; other devices can ask to pair.`
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

// Pairing by code (ADR-0070): the receiver accepts and shows a code; the requester types it on a number pad.
function NumberPad({ onDone, busy }: { onDone: (code: string) => void; busy: boolean }) {
  const [digits, setDigits] = useState("");
  const press = (d: string) => setDigits((v) => (v.length < 6 ? v + d : v));
  const key = (label: string, action: () => void, disabled = false) => (
    <DialogButton key={label} style={{ width: 64, minWidth: 64 }} disabled={busy || disabled} onClick={action}>
      {label}
    </DialogButton>
  );
  return (
    <>
      <Field label={`Code: ${digits.padEnd(6, "_").split("").join(" ")}`} />
      {[["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]].map((row) => (
        <Focusable key={row[0]} style={{ display: "flex", gap: 8, marginBottom: 8 }} flow-children="horizontal">
          {row.map((d) => key(d, () => press(d)))}
        </Focusable>
      ))}
      <Focusable style={{ display: "flex", gap: 8, marginBottom: 8 }} flow-children="horizontal">
        {key("Delete", () => setDigits((v) => v.slice(0, -1)), !digits)}
        {key("0", () => press("0"))}
        {key("OK", () => onDone(digits), digits.length !== 6)}
      </Focusable>
    </>
  );
}

function PairingCard(props: { pairing: Pairing; busy: boolean; run: (work: () => Promise<unknown>, done?: string) => Promise<void> }) {
  const { pairing: p, busy, run } = props;
  const who = p.peerName ?? p.address;
  const cancelButton = (
    <DialogButton style={{ width: "auto" }} onClick={() => void run(() => replicationCancel(p.id))}>
      Cancel
    </DialogButton>
  );
  switch (p.state) {
    case "failed":
      return <Field label={`Pairing with ${who} did not finish`} description={p.reason ?? ""} />;
    case "declined":
      return <Field label={`Not paired with ${who}`} description={p.reason ?? "Declined."} />;
    case "connecting":
      return <Field label={`Connecting to ${who}`} childrenLayout="below">{cancelButton}</Field>;
    case "waiting-accept":
      return (
        <Field label={`Waiting for ${who} to accept`} description="Press Accept on the other device." childrenLayout="below">
          {cancelButton}
        </Field>
      );
    case "enter-code":
      return (
        <Field label={`${who} accepted. Enter the code shown on it.`} childrenLayout="below">
          <NumberPad busy={busy} onDone={(code) => void run(() => replicationEnterCode(p.id, code))} />
          {cancelButton}
        </Field>
      );
    case "request":
      return (
        <Field
          label={`${who} wants to pair`}
          description={`From ${p.address}. Accept only if you are pairing your own device right now.`}
          childrenLayout="below"
        >
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run(() => replicationAnswer(p.id, true))}>
              Accept
            </DialogButton>
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run(() => replicationAnswer(p.id, false))}>
              Decline
            </DialogButton>
          </Focusable>
        </Field>
      );
    case "show-code":
      return (
        <Field label={`Code: ${p.code}`} description={`Type this code on ${who}.`} childrenLayout="below">
          {cancelButton}
        </Field>
      );
    case "checking":
      return <Field label={`Checking the code with ${who}`} />;
    default:
      return null;
  }
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

function size(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.max(0, Math.round(bytes / 1024 ** 2))} MB`;
}

function progress(job: TransferJob): string {
  const done = job.total ? Math.floor((job.received / job.total) * 100) : 0;
  const parts = [`${size(job.received)} of ${size(job.total)} (${done}%)`];
  if (job.state === "running" && job.megabytesPerSecond) {
    parts.push(`${job.megabytesPerSecond} MB/s`);
    if (job.secondsLeft !== null) parts.push(`about ${Math.max(1, Math.round(job.secondsLeft / 60))} min left`);
  }
  if (job.reason) parts.push(job.reason);
  return parts.join(", ");
}

const STATE_TEXT: Record<string, string> = {
  running: "Copying",
  waiting: "Waiting for the other device",
  paused: "Paused",
  verifying: "Checking the copy",
  promoting: "Putting it in place",
  failed: "Stopped with a problem",
};

// Transfers in progress: progress, speed and time left, Pause, Resume and Stop and remove (ADR-0058).
function TransfersSection() {
  const [status, setStatus] = useState<TransfersStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => replicationTransfers().then(setStatus).catch(() => undefined);
  useEffect(() => {
    void refresh();
    const listener = addEventListener(REPLICATION_EVENT, () => void refresh());
    return () => removeEventListener(REPLICATION_EVENT, listener);
  }, []);
  const moving = !!status && status.jobs.some((j) => j.state === "running" || j.state === "verifying" || j.state === "waiting");
  useEffect(() => {
    if (!moving) return;
    const timer = setInterval(() => void refresh(), 2000);
    return () => clearInterval(timer);
  }, [moving]);
  if (!status || status.jobs.length === 0) return null;
  const act = async (work: () => Promise<TransfersStatus>) => {
    setBusy(true);
    try {
      setStatus(await work());
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Field
        label="Transfers"
        description={[status.waitingFor, status.sleepProblem].filter(Boolean).join(" ") || undefined}
      />
      {status.jobs.map((job) => (
        <Field key={job.id} label={`${job.target}: ${STATE_TEXT[job.state] ?? job.state}`} description={progress(job)} childrenLayout="below">
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {job.state === "running" || job.state === "waiting" ? (
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => replicationPause(job.id))}>
                Pause
              </DialogButton>
            ) : job.state === "paused" || job.state === "failed" ? (
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => replicationResume(job.id))}>
                Resume
              </DialogButton>
            ) : null}
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy}
              onClick={() =>
                showModal(
                  <ConfirmModal
                    strTitle="Stop and remove this transfer?"
                    strDescription="Everything this transfer copied so far is deleted. The game already on this device, if any, is not touched. Pause keeps the progress instead."
                    strOKButtonText="Stop and remove"
                    strCancelButtonText="Cancel"
                    onOK={() => void act(() => replicationStop(job.id))}
                  />,
                )
              }
            >
              Stop and remove
            </DialogButton>
          </Focusable>
        </Field>
      ))}
    </>
  );
}

const OFFER_TEXT: Record<string, string> = {
  offered: "Waiting for your answer",
  transferring: "Copying",
  registering: "Adding it to Steam",
  done: "Ready in your library",
  failed: "Stopped with a problem",
};

// Games offered to this device, and games this device offered (ADR-0059).
function OffersSection() {
  const [status, setStatus] = useState<OffersStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => replicationOffers().then(setStatus).catch(() => undefined);
  useEffect(() => {
    void refresh();
    const listener = addEventListener(REPLICATION_EVENT, () => void refresh());
    return () => removeEventListener(REPLICATION_EVENT, listener);
  }, []);
  if (!status) return null;
  const sending = Object.values(status.sending).filter((s) => s.state !== "sent");
  if (!status.incoming.length && !status.outgoing.length && !sending.length) return null;

  const act = async (work: () => Promise<unknown>, done?: string) => {
    setBusy(true);
    try {
      await work();
      if (done) toaster.toast({ title: "Keepsake", body: done });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  const accept = async (offer: IncomingOffer) => {
    const check = await replicationOfferCheck(offer.id, false);
    const start = (copyTool: boolean) =>
      act(() => replicationAccept(offer.id, copyTool), `Copying ${offer.title} from ${offer.from}.`);
    if (!check.problem) return start(false);
    if (offer.toolOffered && check.problem.includes("copy it")) {
      showModal(
        <ConfirmModal
          strTitle={`Copy ${offer.compatTool} too?`}
          strDescription={`This device does not have ${offer.compatTool}, which ${offer.title} uses. Keepsake can copy it from ${offer.from}. Steam finds it after a restart.`}
          strOKButtonText="Copy it too"
          strCancelButtonText="Cancel"
          onOK={() => void start(true)}
        />,
      );
      return;
    }
    toaster.toast({ title: "Keepsake", body: check.problem });
  };

  const applyUpdate = async (offer: IncomingOffer) => {
    try {
      await replicationApplyUpdate(offer.id, false);
      toaster.toast({ title: "Keepsake", body: `Taking the update to ${offer.title}. Your saves and settings stay as they are.` });
      await refresh();
    } catch (err) {
      if (!String(err).includes("changed on this device too")) {
        toaster.toast({ title: "Keepsake", body: String(err) });
        return;
      }
      showModal(
        <ConfirmModal
          strTitle={`${offer.title} changed on both devices`}
          strDescription={`Take theirs replaces this device's copy of the game with the one from ${offer.from}. Keep mine leaves this device's copy and writes nothing. Your saves and settings stay either way.`}
          strOKButtonText="Take theirs"
          strCancelButtonText="Keep mine"
          onOK={() => void act(() => replicationApplyUpdate(offer.id, true), `Taking ${offer.from}'s copy of ${offer.title}.`)}
          onCancel={() => void act(() => replicationKeepMine(offer.id), `${offer.title} stays as it is on this device.`)}
        />,
      );
    }
  };

  const removeGame = (offer: IncomingOffer) =>
    showModal(
      <ConfirmModal
        strTitle={`Stop and remove ${offer.title}?`}
        strDescription="Everything this copy made on this device is deleted: the game's folder, its prefix, a copied compatibility tool and its Steam shortcut. Nothing else is touched."
        strOKButtonText="Stop and remove"
        strCancelButtonText="Cancel"
        onOK={() => void act(() => replicationRemoveGame(offer.id), `${offer.title} removed.`)}
      />,
    );

  return (
    <>
      <Field label="Games between devices" />
      {sending.map((s) => (
        <Field
          key={`sending-${s.title}`}
          label={`${s.title}: ${s.state === "preparing" ? "preparing to send" : "not sent"}`}
          description={s.reason ?? s.warning ?? "Keepsake is checking every file. A large game takes a few minutes."}
        />
      ))}
      {status.incoming.map((offer) => (
        <Field
          key={offer.id}
          label={`${offer.title} from ${offer.from}: ${OFFER_TEXT[offer.state] ?? offer.state}`}
          description={[
            size(offer.bytes),
            offer.compatTool ? `uses ${offer.compatTool}` : "",
            offer.droppedOptions.length ? `launch options left on the other device: ${offer.droppedOptions.join(" ")}` : "",
            offer.reason ?? "",
          ]
            .filter(Boolean)
            .join(". ")}
          childrenLayout="below"
        >
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {offer.state === "offered" && offer.update && (
              <>
                <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void applyUpdate(offer)}>
                  Apply update
                </DialogButton>
                <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => replicationKeepMine(offer.id))}>
                  Keep mine
                </DialogButton>
              </>
            )}
            {offer.state === "offered" && !offer.update && (
              <>
                <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void accept(offer)}>
                  Accept
                </DialogButton>
                <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => replicationDecline(offer.id))}>
                  Decline
                </DialogButton>
              </>
            )}
            {(offer.state === "transferring" || offer.state === "registering" || offer.state === "failed") && !offer.update && (
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => removeGame(offer)}>
                Stop and remove
              </DialogButton>
            )}
            {(offer.state === "transferring" || offer.state === "failed") && offer.update && (
              <DialogButton
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() => void act(() => replicationRemoveGame(offer.id), `The update to ${offer.title} stopped. The game is as it was.`)}
              >
                Stop update
              </DialogButton>
            )}
            {offer.state === "done" && (
              <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => replicationDismiss(offer.id))}>
                Clear from this list
              </DialogButton>
            )}
          </Focusable>
        </Field>
      ))}
      {status.outgoing.map((offer) => (
        <Field key={offer.id} label={`${offer.title}: offered`} description="Waiting for the other device. Withdraw it once it has arrived." childrenLayout="below">
          <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(() => replicationWithdraw(offer.id))}>
            Withdraw
          </DialogButton>
        </Field>
      ))}
    </>
  );
}
