import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { DialogButton, DropdownItem, Field, Focusable, ToggleField } from "@decky/ui";
import { useEffect, useState } from "react";
import {
  RECONNECT_EVENT,
  ReconnectDevice,
  ReconnectStatus,
  reconnectAssist,
  reconnectDiagnose,
  reconnectDismiss,
  reconnectExport,
  reconnectReadUsb,
  reconnectSetDryRun,
  reconnectSetHelp,
  reconnectSetOption,
  reconnectStatus,
} from "../backend";
import { plainError } from "../format";
import { CablePairing, HelperCard, SspGateCard } from "./ReconnectHelper";

// Device, Reconnect help (R22, ADR-0082): for Bluetooth Classic controllers that pair but do not
// reconnect. Every paired device is listed; help acts only on the ones the user turns it on for,
// by adapter and address. Nothing is inferred from a device's name, class or modalias.

const key = (d: ReconnectDevice) => `${d.adapter}/${d.mac}`;

function details(d: ReconnectDevice): string {
  const parts = [
    d.transport === "bredr" ? "Bluetooth Classic" : d.transport === "le" ? "Bluetooth LE" : "Bluetooth",
    d.class ? `class ${d.class}` : "",
    d.modalias ?? "",
    d.adapterName,
    d.connected ? "connected" : "not connected",
  ];
  let text = parts.filter(Boolean).join(", ");
  if (d.unregisteredPrefix) text += ". Its address is not from a registered manufacturer (common for clones; information only)";
  if (d.last) text += `. Last diagnosis: ${d.last.title}`;
  return text + ".";
}

export function ReconnectPanel() {
  const [s, setS] = useState<ReconnectStatus | null>(null);
  const [adapter, setAdapter] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [step, setStep] = useState<string | null>(null);

  const load = () =>
    reconnectStatus()
      .then(setS)
      .catch(() => undefined);
  useEffect(() => {
    void load();
    const listener = addEventListener(RECONNECT_EVENT, () => void load());
    return () => {
      removeEventListener(RECONNECT_EVENT, listener);
    };
  }, []);

  const run = async (label: string, work: () => Promise<unknown>) => {
    setBusy(label);
    try {
      await work();
    } catch (err) {
      toaster.toast({ title: "Reconnect help", body: plainError(err) });
    } finally {
      setBusy(null);
      void load();
    }
  };

  if (!s) return null;
  if (!s.available) return <Field label="Reconnect help" description={s.problem ?? "Bluetooth could not be read."} />;

  const adapters = s.adapters ?? [];
  const chosen = adapter ?? adapters[0]?.address ?? null;
  const devices = (s.devices ?? []).filter((d) => d.adapter === chosen);
  const suggested = devices.filter((d) => d.suggest && !d.help);

  return (
    <>
      <Field
        label="Reconnect help"
        description="For controllers that pair but will not reconnect with their normal button, often clones. Turn help on only for the controllers that need it: the others are never touched."
      />
      <HelperCard s={s} reload={() => void load()} />
      {s.helper?.ready && (s.sspGate?.on || (s.devices ?? []).some((d) => d.help && d.last?.outcome === "O3")) && (
        <SspGateCard s={s} reload={() => void load()} />
      )}
      {adapters.length > 1 && (
        <DropdownItem
          label="Bluetooth adapter"
          rgOptions={adapters.map((a) => ({ data: a.address, label: `${a.name}${a.alias ? ` (${a.alias})` : ""}` }))}
          selectedOption={chosen}
          onChange={(o) => setAdapter(String(o.data))}
        />
      )}
      {suggested.map((d) => (
        <Field key={`s-${key(d)}`} label={`${d.name} may need help`} description={`${d.suggest?.reason}. Run a diagnosis?`}>
          <Focusable style={{ display: "flex", gap: 8 }}>
            <DialogButton
              onClick={() =>
                void run("help", async () => {
                  await reconnectSetHelp(d.adapter, d.mac, true, d.name);
                  setOpen(key(d));
                })
              }
            >
              Turn on help
            </DialogButton>
            <DialogButton onClick={() => void run("dismiss", () => reconnectDismiss(d.adapter, d.mac))}>Dismiss</DialogButton>
          </Focusable>
        </Field>
      ))}
      {devices.length === 0 && <Field label="No paired devices" description="Pair a controller in Steam's Bluetooth settings first." />}
      {devices.map((d) => (
        <div key={key(d)}>
          <ToggleField
            label={d.name}
            description={d.transport === "le" ? `${details(d)} Bluetooth LE controllers are not supported yet.` : details(d)}
            checked={d.help}
            disabled={busy !== null || d.transport === "le"}
            onChange={(on) =>
              void run("help", async () => {
                await reconnectSetHelp(d.adapter, d.mac, on, d.name);
                setOpen(on ? key(d) : null);
              })
            }
          />
          {d.help && (
            <Field childrenContainerWidth="max">
              <Focusable style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <DialogButton onClick={() => setOpen(open === key(d) ? null : key(d))}>{open === key(d) ? "Hide" : "Help options"}</DialogButton>
                <DialogButton
                  disabled={busy !== null}
                  onClick={() =>
                    void run("assist", async () => {
                      toaster.toast({ title: "Reconnect help", body: "Looking for the controller for up to 30 seconds." });
                      const r = await reconnectAssist(d.adapter, d.mac);
                      toaster.toast({ title: "Reconnect help", body: r.message });
                    })
                  }
                >
                  {busy === "assist" ? "Looking" : "Reconnect"}
                </DialogButton>
              </Focusable>
            </Field>
          )}
          {d.help && open === key(d) && (
            <>
              <Field
                label="Reconnect"
                description="Put the controller in pairing mode first (on a DualShock 4, hold Share and PS until the light flashes quickly), then select Reconnect. Its existing pairing is used: nothing is forgotten."
              />
              <ToggleField
                label="Pair and commit"
                description="When you pair this controller, Keepsake connects to it at once so that the controller saves the pairing. It acts once per pairing and never when the controller is already connected."
                checked={d.commit}
                disabled={busy !== null}
                onChange={(on) => void run("option", () => reconnectSetOption(d.adapter, d.mac, "commit", on))}
              />
              {(d.modalias ?? "").toUpperCase().includes("V054C") && (
                <ToggleField
                  label="Full report mode"
                  description="Some DualShock 4 clones send reduced reports until asked. Keepsake asks each time this controller connects."
                  checked={d.fullMode}
                  disabled={busy !== null}
                  onChange={(on) => void run("option", () => reconnectSetOption(d.adapter, d.mac, "fullMode", on))}
                />
              )}
              <Field
                label="Diagnose"
                description={
                  step === key(d)
                    ? "Watching for 45 seconds. Press the controller's button once now."
                    : "Turn the controller off and wait 10 seconds. Then select Start and press the controller's normal button once."
                }
              >
                <DialogButton
                  disabled={busy !== null}
                  onClick={() =>
                    void run("diagnose", async () => {
                      setStep(key(d));
                      try {
                        const r = await reconnectDiagnose(d.adapter, d.mac);
                        toaster.toast({ title: r.title, body: r.advice });
                      } finally {
                        setStep(null);
                      }
                    })
                  }
                >
                  {busy === "diagnose" ? "Watching" : "Start"}
                </DialogButton>
              </Field>
              {d.last && <Field label={d.last.title} description={`${d.last.advice} Seen: ${d.last.evidence.join("; ") || "nothing"}.`} />}
              {s.cableReady && (
                <Field label="Read stored host over USB" description="With the controller on a USB data cable: checks which host it will call. Only a controller whose own address matches this device is read.">
                  <DialogButton
                    disabled={busy !== null}
                    onClick={() =>
                      void run("usb", async () => {
                        const r = await reconnectReadUsb(d.adapter, d.mac);
                        toaster.toast({
                          title: "Reconnect help",
                          body: r.read.ok ? (r.read.storesThisHandheld ? "The controller stores this handheld." : "The controller stores a different host.") : (r.read.message ?? "Not read."),
                        });
                      })
                    }
                  >
                    Read
                  </DialogButton>
                </Field>
              )}
              {d.captured && (
                <Field label="Export report bundle" description="The last diagnosis, the journal lines and this device's details in one zip, to share on a BlueZ or community issue. This handheld's address is replaced.">
                  <DialogButton
                    disabled={busy !== null}
                    onClick={() =>
                      void run("export", async () => {
                        const r = await reconnectExport(d.adapter, d.mac, true);
                        toaster.toast({ title: "Report saved", body: r.where });
                      })
                    }
                  >
                    Export
                  </DialogButton>
                </Field>
              )}
              {s.helper?.ready ? (
                <CablePairing d={d} cableReady={Boolean(s.cableReady)} reload={() => void load()} />
              ) : (
                <Field label="Cable pairing" description="Needs the Keepsake Helper (above)." />
              )}
            </>
          )}
        </div>
      ))}
      <ToggleField
        label="Dry run"
        description="Log what reconnect help would do without connecting or scanning."
        checked={Boolean(s.dryRun)}
        disabled={busy !== null}
        onChange={(on) => void run("dry", () => reconnectSetDryRun(on))}
      />
      {(s.actions ?? []).length > 0 && (
        <Field
          label="Recent actions"
          description={(s.actions ?? [])
            .slice(-5)
            .reverse()
            .map((a) => `${a.at.replace("T", " ").replace("Z", "")} ${a.action}${a.device ? ` ${a.device}` : ""}`)
            .join("; ")}
        />
      )}
    </>
  );
}
