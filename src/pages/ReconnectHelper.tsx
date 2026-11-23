import { toaster } from "@decky/api";
import { DialogButton, DropdownItem, Field, Focusable, ToggleField } from "@decky/ui";
import { useState } from "react";
import {
  ReconnectDevice,
  ReconnectStatus,
  helperPrepare,
  reconnectCablePair,
  reconnectCableRestore,
  reconnectSetSspGate,
  reconnectSspConfirm,
} from "../backend";
import { plainError } from "../format";
import { handOff, handOffAvailable, reasonText } from "../update";

// Reconnect help's root jobs (R23, ADR-0083), through the separate Haversack Helper plugin.
// Every step that restarts Bluetooth or lowers its security asks twice.

const toast = (body: string): void => {
  toaster.toast({ title: "Reconnect help", body });
};

export function HelperCard({ s, reload }: { s: ReconnectStatus; reload: () => void }) {
  const [busy, setBusy] = useState(false);
  const h = s.helper;
  const install = async () => {
    setBusy(true);
    try {
      const prepared = await helperPrepare();
      if (!prepared.ok) toast(reasonText(prepared.reason));
      else if (!handOffAvailable()) toast(`Install it from Decky's Developer page, Install plugin from URL: ${prepared.artifact}`);
      else await handOff(prepared);
    } catch (err) {
      toast(plainError(err));
    } finally {
      setBusy(false);
      reload();
    }
  };
  if (h?.ready) return <Field label="Haversack Helper" description={`Ready (version ${h.version}). It runs as root and does only the jobs below.`} />;
  const update = h?.problem === "version";
  return (
    <Field
      label="Haversack Helper"
      description={
        update
          ? `The helper is version ${h?.helper}; it must match Haversack. Update it.`
          : "Cable pairing, the SSP gate and the Bluetooth capture need root. They run in a small separate plugin, signed with Haversack's release key and locked to this version, so Haversack itself never runs as root. Decky asks you to confirm the install."
      }
    >
      <DialogButton disabled={busy} onClick={() => void install()}>
        {busy ? "Checking" : update ? "Update helper" : "Install helper"}
      </DialogButton>
    </Field>
  );
}

export function CablePairing({ d, cableReady, reload }: { d: ReconnectDevice; cableReady: boolean; reload: () => void }) {
  const [confirm, setConfirm] = useState<"pair" | "restore" | null>(null);
  const [reversed, setReversed] = useState(false);
  const [busy, setBusy] = useState(false);
  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    try {
      await work();
    } catch (err) {
      toast(plainError(err));
    } finally {
      setBusy(false);
      setConfirm(null);
      reload();
    }
  };
  const stored = d.stored;
  return (
    <>
      {stored && (
        <Field
          label="This handheld's pairing"
          description={[
            stored.linkKey ? `a key is stored (type ${stored.keyType ?? "unknown"})` : "no key is stored",
            stored.trusted ? "trusted" : "not trusted",
            stored.services ? "its services are known" : "its services are not known yet: use Reconnect once in pairing mode first",
            stored.backups ? `${stored.backups} backup${stored.backups === 1 ? "" : "s"}` : "",
          ]
            .filter(Boolean)
            .join(", ")}
        />
      )}
      <Field
        label="Cable pairing"
        description={
          confirm === "pair"
            ? "Bluetooth restarts: every Bluetooth device disconnects for a few seconds. Select Confirm to go ahead."
            : cableReady
              ? "Gives the controller and this handheld the same new key over the cable, then restarts Bluetooth. Keep the controller plugged in until it finishes. Not while a game runs."
              : "Connect this controller with a USB data cable. Cable pairing is supported for DualShock 4 controllers (and clones that use their IDs)."
        }
      >
        <DialogButton
          disabled={busy || !cableReady}
          onClick={() =>
            confirm === "pair"
              ? void run(async () => {
                  toast((await reconnectCablePair(d.adapter, d.mac, reversed ? "reversed" : "same")).message);
                })
              : setConfirm("pair")
          }
        >
          {busy && confirm === "pair" ? "Pairing" : confirm === "pair" ? "Confirm" : "Cable pair"}
        </DialogButton>
      </Field>
      <ToggleField
        label="Reversed key order (advanced)"
        description="One controlled experiment if the controller still fails to authenticate after cable pairing: the key is stored on this handheld in the reverse byte order."
        checked={reversed}
        disabled={busy}
        onChange={setReversed}
      />
      {stored && stored.backups > 0 && (
        <Field
          label="Restore backup"
          description={confirm === "restore" ? "Bluetooth restarts. Select Confirm to put back the pairing from before the last cable pairing." : "Puts back the pairing file from before the last cable pairing."}
        >
          <DialogButton
            disabled={busy}
            onClick={() =>
              confirm === "restore"
                ? void run(async () => {
                    await reconnectCableRestore(d.adapter, d.mac);
                    toast("The backup was restored.");
                  })
                : setConfirm("restore")
            }
          >
            {confirm === "restore" ? "Confirm" : "Restore"}
          </DialogButton>
        </Field>
      )}
    </>
  );
}

export function SspGateCard({ s, reload }: { s: ReconnectStatus; reload: () => void }) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const adapters = s.adapters ?? [];
  const [adapter, setAdapter] = useState<string | null>(null);
  const gate = s.sspGate;
  const chosen = adapter ?? adapters[0]?.address ?? "";
  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await work();
    } catch (err) {
      toast(plainError(err));
    } finally {
      setBusy(false);
      setStep(0);
      reload();
    }
  };
  return (
    <>
      <ToggleField
        label="SSP gate"
        description={
          gate?.on
            ? `On: Secure Simple Pairing is on only while pairing (now: ${gate.state}). Switch it off to put normal security back.`
            : "For controllers that the diagnosis says are refused while security starts (O3). Off by default."
        }
        checked={Boolean(gate?.on) || step > 0}
        disabled={busy}
        onChange={(on) => (on ? setStep(1) : void run(() => reconnectSetSspGate(false, "", "")))}
      />
      {step === 1 && (
        <Field
          label="Read this first"
          description="The SSP gate lowers Bluetooth security for the whole adapter, for every device, not just this controller. While it is on, new pairings use the older PIN method and Bluetooth's Secure Connections protection is lost. SSP goes back on while pairing, when you switch the gate off, and if Haversack stops."
        >
          <DialogButton onClick={() => setStep(2)}>Continue</DialogButton>
        </Field>
      )}
      {step === 2 && (
        <>
          {adapters.length > 1 && (
            <DropdownItem
              label="Adapter"
              rgOptions={adapters.map((a) => ({ data: a.address, label: a.name }))}
              selectedOption={chosen}
              onChange={(o) => setAdapter(String(o.data))}
            />
          )}
          <Field label="Turn on the SSP gate?" description="Select I understand to turn it on, or Cancel.">
            <Focusable style={{ display: "flex", gap: 8 }}>
              <DialogButton disabled={busy} onClick={() => void run(() => reconnectSetSspGate(true, chosen, "I understand"))}>
                I understand
              </DialogButton>
              <DialogButton onClick={() => setStep(0)}>Cancel</DialogButton>
            </Focusable>
          </Field>
        </>
      )}
      {gate?.state === "needs-confirm" && (
        <Field label="SSP needs the adapter restarted" description="Turning SSP off here needs Bluetooth switched off and on, which drops connected devices for a moment.">
          <DialogButton disabled={busy} onClick={() => void run(() => reconnectSspConfirm())}>
            Restart Bluetooth
          </DialogButton>
        </Field>
      )}
    </>
  );
}
