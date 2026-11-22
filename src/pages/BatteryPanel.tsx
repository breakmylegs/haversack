import { Field, PanelSectionRow, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { ChargeLimitStatus, deviceBattery, deviceSetChargeLimit } from "../backend";
import { plainError } from "../format";

// The 80 percent charge limit (R21 stage 4, ADR-0077), through steamos-manager only. Where it is
// not offered there, the state is shown with where to change it.

const DEVICE_EVENT = "keepsake_device";

export function BatteryPanel({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<ChargeLimitStatus | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const load = () =>
      deviceBattery()
        .then(setStatus)
        .catch(() => undefined);
    void load();
    const listener = addEventListener(DEVICE_EVENT, () => void load());
    return () => removeEventListener(DEVICE_EVENT, listener);
  }, []);
  if (!status) return null;
  const toggle = (on: boolean) => {
    setBusy(true);
    deviceSetChargeLimit(on)
      .then(setStatus)
      .catch((err) => toaster.toast({ title: "Keepsake", body: plainError(err) }))
      .finally(() => setBusy(false));
  };
  const controllable = status.control === "steamos-manager";
  if (compact) {
    return controllable ? (
      <PanelSectionRow>
        <ToggleField label="Stop charging at 80%" checked={Boolean(status.limited)} disabled={busy} onChange={toggle} />
      </PanelSectionRow>
    ) : null;
  }
  const state = status.limited == null ? "unknown" : status.limited ? "on" : "off";
  return (
    <>
      <Field
        label="Battery care"
        description="Stopping at 80% keeps the battery healthier if the device is plugged in for long spells. It is Lenovo's only charge limit on the Legion Go and Go 2."
      />
      {controllable ? (
        <ToggleField label="Stop charging at 80%" checked={Boolean(status.limited)} disabled={busy} onChange={toggle} />
      ) : (
        <Field
          label={`Charge limit: ${state}`}
          description={`This device's steamos-manager does not let Keepsake change it. ${status.where ?? ""}`}
        />
      )}
      {status.firmware.chargeTypes && <Field label="Firmware" description={`Charge types: ${status.firmware.chargeTypes}`} />}
    </>
  );
}
