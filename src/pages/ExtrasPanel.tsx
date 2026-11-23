import { Field, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { deviceExtras, DeviceExtras, deviceSetWifiPowerSaving } from "../backend";
import { plainError } from "../format";

// Device, Other (R21 stage 6, ADR-0079): Wi-Fi power saving through steamos-manager, the BIOS
// check, and where the display settings live (Steam owns them).

export function ExtrasPanel() {
  const [s, setS] = useState<DeviceExtras | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    deviceExtras()
      .then(setS)
      .catch(() => undefined);
  }, []);
  if (!s) return null;
  const bios = s.bios;
  return (
    <>
      {s.wifiPowerSaving != null ? (
        <ToggleField
          label="Wi-Fi power saving"
          description="Saves battery. Turn it off if streaming or online games stutter."
          checked={s.wifiPowerSaving}
          disabled={busy}
          onChange={(on) => {
            setBusy(true);
            deviceSetWifiPowerSaving(on)
              .then(setS)
              .catch((err) => toaster.toast({ title: "Haversack", body: plainError(err) }))
              .finally(() => setBusy(false));
          }}
        />
      ) : (
        <Field label="Wi-Fi power saving" description="This device's steamos-manager does not offer it." />
      )}
      <Field
        label={`BIOS ${bios.version ?? "unknown"}`}
        description={
          bios.notes.length
            ? bios.notes.join(" ")
            : bios.known
              ? "Haversack knows of no problems with this BIOS."
              : "Haversack has no BIOS notes for this model."
        }
      />
      <Field
        label="Display"
        description="Refresh rate, frame limit and brightness are in Steam's own quick access menu, under Performance and Display. Haversack leaves them to Steam."
      />
    </>
  );
}
