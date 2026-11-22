import { Field } from "@decky/ui";
import { useEffect, useState } from "react";
import { ControllersStatus, deviceControllers } from "../backend";

// Device, Controllers (R21 stage 5, ADR-0078): what the kernel shows of the Legion controllers,
// read-only. Remapping, dead zones and gyro are Steam Input's; changing the controllers' own
// settings and RGB needs root, which waits for a decision (ADR-0075 tier 1).

const WORDS: Record<string, string> = {
  mode: "Mode",
  os_mode: "System mode",
  rumble_intensity: "Rumble",
  fps_mode_dpi: "FPS mode DPI",
  firmware_version: "Firmware",
  imu_enabled: "Gyro",
  auto_sleep_time: "Auto-sleep",
  rumble_mode: "Rumble mode",
  enabled: "On",
  vibration_enabled: "Haptics",
  vibration_intensity: "Haptic strength",
  effect: "Effect",
  speed: "Speed",
  brightness: "Brightness",
  profile: "Profile",
};

function line(values: Record<string, string>): string {
  return Object.entries(values)
    .filter(([k]) => k in WORDS)
    .map(([k, v]) => `${WORDS[k]} ${v}`)
    .join(", ");
}

export function ControllersPanel() {
  const [s, setS] = useState<ControllersStatus | null>(null);
  useEffect(() => {
    deviceControllers()
      .then(setS)
      .catch(() => undefined);
  }, []);
  if (!s) return null;
  return (
    <>
      {s.batteries.length > 0 ? (
        s.batteries.map((b) => (
          <Field
            key={b.name}
            label={b.name}
            description={`${b.percent != null ? `${b.percent}%` : (b.level ?? "unknown")}${b.status ? `, ${b.status.toLowerCase()}` : ""}`}
          />
        ))
      ) : (
        <Field label="Controller batteries" description="This system does not show them yet (the Legion controller driver arrives in kernel 7.1)." />
      )}
      {s.controllers.map((c) => (
        <Field
          key={c.id}
          label="Controller settings"
          description={[line(c.settings), c.left.imu_enabled != null ? `left: ${line(c.left)}` : "", c.right.imu_enabled != null ? `right: ${line(c.right)}` : "", Object.keys(c.touchpad).length ? `touchpad: ${line(c.touchpad)}` : ""]
            .filter(Boolean)
            .join(". ")}
        />
      ))}
      {s.rings && <Field label="Stick lights" description={line(s.rings) || "Shown by the kernel."} />}
      {s.tools.length > 0 && <Field label="Managed by" description={s.tools.join(", ")} />}
      <Field
        label="Changing them"
        description="Remap buttons, set dead zones and use the gyro in Steam's controller settings. Changing the controllers' own settings and the stick lights needs a separate helper that runs as root, which is waiting for a decision."
      />
    </>
  );
}
