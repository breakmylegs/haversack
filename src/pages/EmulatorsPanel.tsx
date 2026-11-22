import { toaster } from "@decky/api";
import { DialogButton, DropdownItem, Field, ToggleField } from "@decky/ui";
import { useEffect, useState } from "react";
import { EmulatorSetup, emulatorSend, emulatorSetup, PairedDevice, replicationStatus } from "../backend";
import { plainError, sizeText } from "../format";

// Games and devices, Emulators (R26, ADR-0087): what this device has, and sending a game to your other
// handheld. The game always travels; the emulator and its settings only where the other device lacks
// them; firmware, BIOS and keys only when you tick the separate box, and only straight to your own
// paired device. Nothing already on the other device is replaced.

const SETUP_WORDS: Record<string, string> = { emudeck: "EmuDeck", retrodeck: "RetroDECK" };
const TYPE_WORDS: Record<string, string> = { appimage: "AppImage", binary: "program", flatpak: "Flatpak" };

export function EmulatorsPanel() {
  const [s, setS] = useState<EmulatorSetup | null>(null);
  const [peers, setPeers] = useState<PairedDevice[]>([]);
  const [peer, setPeer] = useState<string | null>(null);
  const [withKeys, setWithKeys] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    emulatorSetup()
      .then(setS)
      .catch(() => undefined);
    replicationStatus()
      .then((r) => {
        setPeers(r.peers);
        if (r.peers.length) setPeer(r.peers[0].id);
      })
      .catch(() => undefined);
  }, []);
  if (!s) return <Field label="Emulators" description="Looking" />;
  if (s.off) return <Field label="Emulators" description={s.problem ?? "Replication is off."} />;
  const systems = Object.entries(s.perSystem).sort((a, b) => b[1] - a[1]);
  const secrets = Object.entries(s.secrets);
  const target = peers.find((p) => p.id === peer);
  const send = async (system: string, name: string) => {
    if (busy || !peer) return; // never disable a focused button: ignore a second press
    setBusy(`${system}/${name}`);
    try {
      const r = await emulatorSend(peer, system, name, withKeys);
      toaster.toast({ title: "Emulators", body: `Getting ${name} ready to send (${r.parts.join(", ")}).` });
    } catch (err) {
      toaster.toast({ title: "Emulators", body: plainError(err) });
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Field
        label="On this device"
        description={
          s.setups.length || s.emulators.length
            ? [
                s.setups.length ? `Set up with ${s.setups.map((x) => SETUP_WORDS[x] ?? x).join(" and ")}` : "No EmuDeck or RetroDECK",
                `${s.emulators.length} emulator${s.emulators.length === 1 ? "" : "s"}`,
                `${s.games.length} game${s.games.length === 1 ? "" : "s"}`,
              ].join(", ")
            : "No emulator setup was found. Keepsake looks for EmuDeck, RetroDECK and the common standalone emulators."
        }
      />
      {s.emulators.map((e) => (
        <Field key={e.name} label={e.name} description={`${TYPE_WORDS[e.type] ?? e.type}, for ${e.system}`} />
      ))}
      {secrets.length > 0 && (
        <Field
          label="Firmware, BIOS and keys"
          description={`${secrets.map(([k, n]) => `${n} for ${k}`).join(", ")}. Counted only: Keepsake never reads them.`}
        />
      )}
      {peers.length === 0 ? (
        <Field label="Send to your other handheld" description="Pair your other handheld first, in Games and devices, Other devices." />
      ) : (
        <>
          {peers.length > 1 && (
            <DropdownItem
              label="Send to"
              rgOptions={peers.map((p) => ({ data: p.id, label: p.name }))}
              selectedOption={peer}
              onChange={(o) => setPeer(String(o.data))}
            />
          )}
          <ToggleField
            label="Also send firmware and keys"
            description={`Only straight to ${target?.name ?? "your other handheld"} over the encrypted link, stored there for your user only. Never to the cloud, logs or exports. Copy only what you own.`}
            checked={withKeys}
            onChange={setWithKeys}
          />
        </>
      )}
      {systems.map(([system, count]) => (
        <div key={system}>
          <Field label={`${system}: ${count} game${count === 1 ? "" : "s"}`} />
          {s.games
            .filter((g) => g.system === system)
            .slice(0, 50)
            .map((g) => (
              <Field key={`${system}/${g.name}`} label={g.name} description={`${sizeText(g.size)}${g.files > 1 ? `, ${g.files} files` : ""}`}>
                {peer && (
                  <DialogButton onClick={() => void send(system, g.name)}>
                    {busy === `${system}/${g.name}` ? "Sending" : `Send to ${target?.name ?? "other handheld"}`}
                  </DialogButton>
                )}
              </Field>
            ))}
        </div>
      ))}
    </>
  );
}
