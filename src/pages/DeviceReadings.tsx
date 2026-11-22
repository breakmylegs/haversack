import { Field } from "@decky/ui";
import { useEffect, useState } from "react";
import { deviceReadings, DeviceReadings as Readings } from "../backend";

// Device, Status, live readings (R21 stage 1, ADR-0074): temperatures, fans, power, the
// firmware mode, BIOS and CPU state, every 2 seconds while the tab is open. Read-only.

const CHIP_NAMES: Record<string, string> = {
  k10temp: "CPU",
  amdgpu: "GPU",
  nvme: "SSD",
  acpitz: "Board",
  BAT0: "Battery",
};

export function DeviceReadings() {
  const [r, setR] = useState<Readings | null>(null);
  useEffect(() => {
    let live = true;
    const load = () =>
      deviceReadings()
        .then((x) => live && setR(x))
        .catch(() => undefined);
    void load();
    const timer = setInterval(() => void load(), 2000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  if (!r) return null;
  const temps = r.chips.flatMap((c) =>
    c.temps.slice(0, 3).map((t) => `${CHIP_NAMES[c.name] ?? c.name}${c.temps.length > 1 ? ` ${t.label}` : ""} ${t.value.toFixed(0)} °C`),
  );
  const fans = r.chips.flatMap((c) => c.fans.map((f) => `${f.value.toFixed(0)} RPM`));
  const power = [
    r.battery.watts != null ? `${r.battery.watts} W ${r.battery.mains ? "from the charger" : "from the battery"}` : "",
    r.gpuWatts != null ? `GPU ${r.gpuWatts} W` : "",
  ].filter(Boolean);
  return (
    <>
      <Field label="Temperatures" description={temps.join(", ") || "None readable."} />
      <Field label="Fan" description={fans.join(", ") || "No fan speed is readable on this system yet."} />
      {power.length > 0 && <Field label="Power" description={power.join(", ")} />}
      <Field
        label="Performance mode"
        description={
          r.profile ? `${r.profile.words} (${r.profile.current}). Available: ${r.profile.choices.join(", ")}.` : "This system does not expose the firmware mode."
        }
      />
      <Field
        label="Processor"
        description={[
          r.cpu.online ? `${r.cpu.online} threads online` : "",
          r.cpu.smt ? `SMT ${r.cpu.smt}` : "",
          r.cpu.boost == null ? "" : `boost ${r.cpu.boost ? "on" : "off"}`,
        ]
          .filter(Boolean)
          .join(", ") || "Unknown."}
      />
      {r.battery.chargeLimit != null && <Field label="Charge limit" description={`${r.battery.chargeLimit}%`} />}
      <Field label="BIOS" description={r.bios.version ? `${r.bios.version}${r.bios.date ? `, ${r.bios.date}` : ""}` : "Unknown."} />
    </>
  );
}
