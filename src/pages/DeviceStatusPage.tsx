import { Field } from "@decky/ui";
import { useEffect, useState } from "react";
import { deviceStatus, DeviceStatus } from "../backend";
import { DeviceReadings } from "./DeviceReadings";

// Device, Status (layout v3, ADR-0073): this handheld as Keepsake sees it. Read-only. The device
// controls (R21) add Power, Fans, Battery, Controllers and Display beside it, stage by stage.

export function DeviceStatusPage() {
  const [status, setStatus] = useState<DeviceStatus | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    deviceStatus()
      .then(setStatus)
      .catch(() => setFailed(true));
  }, []);
  if (failed) return <Field label="This device" description="Keepsake could not read this device's details." />;
  if (!status) return <Field label="This device" description="Loading" />;
  const battery = status.battery;
  const batteryText = !battery.present
    ? "No battery: this device runs on mains power."
    : `${battery.percent ?? "Unknown"}%${battery.mains ? ", charging or on mains power" : ", on battery"}`;
  const display = status.display;
  return (
    <div>
      <Field
        label={`${status.vendor ? `${status.vendor} ` : ""}${status.model}`}
        description={
          status.how === "generic"
            ? "Keepsake does not have a profile for this model, so it uses safe generic limits."
            : status.how === "override"
              ? "Chosen in Advisor's settings."
              : "Recognised from the device's model strings."
        }
      />
      {status.apu && <Field label="Processor" description={status.apu} />}
      {status.tdp.min != null && status.tdp.max != null && (
        <Field label="Power range" description={`${status.tdp.min} to ${status.tdp.max} W`} />
      )}
      {display.width && display.height && (
        <Field
          label="Screen"
          description={`${display.width} x ${display.height}${display.refresh_hz_max ? `, up to ${display.refresh_hz_max} Hz` : ""}${display.vrr ? ", variable refresh rate" : ""}`}
        />
      )}
      <Field label="Battery" description={batteryText} />
      <DeviceReadings />
      <Field
        label="Device controls"
        description="Performance modes, TDP and CPU boost are on the Power tab, and the charge limit on the Battery tab, the controllers on the Controllers tab, and Wi-Fi power saving and the BIOS check on the Other tab. Fan controls need root and wait for a decision."
      />
    </div>
  );
}
