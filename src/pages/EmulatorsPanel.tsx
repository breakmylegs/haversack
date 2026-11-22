import { Field } from "@decky/ui";
import { useEffect, useState } from "react";
import { EmulatorSetup, emulatorSetup } from "../backend";
import { sizeText } from "../format";

// Games and devices, Emulators (R26 stage 1, ADR-0087): what this device has, read-only. Copying
// games, emulators, firmware and keys to the other device comes in the next stage. Key and firmware
// files are counted by name and place: their contents are never read.

const SETUP_WORDS: Record<string, string> = { emudeck: "EmuDeck", retrodeck: "RetroDECK" };
const TYPE_WORDS: Record<string, string> = { appimage: "AppImage", binary: "program", flatpak: "Flatpak" };

export function EmulatorsPanel() {
  const [s, setS] = useState<EmulatorSetup | null>(null);
  useEffect(() => {
    emulatorSetup()
      .then(setS)
      .catch(() => undefined);
  }, []);
  if (!s) return <Field label="Emulators" description="Looking" />;
  if (s.off) return <Field label="Emulators" description={s.problem ?? "Replication is off."} />;
  const systems = Object.entries(s.perSystem).sort((a, b) => b[1] - a[1]);
  const secrets = Object.entries(s.secrets);
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
      {systems.map(([system, count]) => (
        <Field
          key={system}
          label={`${system}: ${count} game${count === 1 ? "" : "s"}`}
          description={s.games
            .filter((g) => g.system === system)
            .slice(0, 6)
            .map((g) => `${g.name} (${sizeText(g.size)})`)
            .join(", ")}
        />
      ))}
      {secrets.length > 0 && (
        <Field
          label="Firmware, BIOS and keys"
          description={`${secrets.map(([k, n]) => `${n} for ${k}`).join(", ")}. Counted only: Keepsake never reads them, and they will only ever travel straight to your own paired device.`}
        />
      )}
      <Field
        label="Copying to your other device"
        description="Copying games, emulators, settings, firmware and keys to your other handheld comes in the next release."
      />
    </>
  );
}
