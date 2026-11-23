import { toaster } from "@decky/api";
import { DialogButton, DropdownItem, Field, SliderField, ToggleField } from "@decky/ui";
import { useEffect, useState } from "react";
import { ControllerSettingsStatus, controllerSettingsForget, controllerSettingsSet, controllerSettingsStatus } from "../backend";
import { plainError } from "../format";

// Device, Controllers (R24, ADR-0086): the Legion controllers' own settings and the stick lights,
// changed through the Haversack Helper and the kernel's hid-lenovo-go driver. Each change is applied
// at once; "Keep" makes Haversack apply it again whenever the controller comes back.

const toast = (body: string): void => {
  toaster.toast({ title: "Controllers", body });
};
const CHOICES: Record<string, { label: string; options: [string, string][] }> = {
  mode: { label: "Controller mode", options: [["xinput", "XInput"], ["dinput", "DirectInput"]] },
  os_mode: { label: "Button chords for", options: [["linux", "Linux"], ["windows", "Windows"]] },
  rumble_intensity: { label: "Rumble", options: [["off", "Off"], ["low", "Low"], ["medium", "Medium"], ["high", "High"]] },
  fps_mode_dpi: { label: "FPS mode mouse DPI", options: [["500", "500"], ["800", "800"], ["1200", "1200"], ["1800", "1800"]] },
  "left_handle/rumble_mode": {
    label: "Left rumble style",
    options: [["standard", "Standard"], ["fps", "FPS"], ["racing", "Racing"], ["spg", "Sports"], ["rpg", "RPG"]],
  },
  "right_handle/rumble_mode": {
    label: "Right rumble style",
    options: [["standard", "Standard"], ["fps", "FPS"], ["racing", "Racing"], ["spg", "Sports"], ["rpg", "RPG"]],
  },
  "touchpad/vibration_intensity": { label: "Touchpad haptic strength", options: [["off", "Off"], ["low", "Low"], ["medium", "Medium"], ["high", "High"]] },
  "led/effect": { label: "Light effect", options: [["monocolor", "Solid"], ["breathe", "Breathe"], ["chroma", "Colour cycle"], ["rainbow", "Rainbow"]] },
};
const TOGGLES: Record<string, string> = {
  "left_handle/imu_enabled": "Left controller gyro",
  "touchpad/enabled": "Touchpad",
  "touchpad/vibration_enabled": "Touchpad haptics",
  "led/enabled": "Stick lights",
};
const SLEEP: [string, string][] = [["0", "Never"], ["5", "5 min"], ["10", "10 min"], ["15", "15 min"], ["30", "30 min"], ["60", "60 min"]];

export function ControllerSettingsPanel() {
  const [s, setS] = useState<ControllerSettingsStatus | null>(null);
  const [keep, setKeep] = useState(true);
  const [busy, setBusy] = useState(false);
  const [rgb, setRgb] = useState<[number, number, number] | null>(null);
  useEffect(() => {
    controllerSettingsStatus()
      .then((next) => {
        setS(next);
        const parts = next.current?.["led/multi_intensity"]?.split(" ").map(Number);
        if (parts && parts.length === 3) setRgb([parts[0], parts[1], parts[2]]);
      })
      .catch(() => undefined);
  }, []);
  if (!s || s.off) return null;
  if (!s.present) return <Field label="Changing the controllers" description="Needs the Legion controllers on the kernel's hid-lenovo-go driver (kernel 7.1 and later, and on the Legion Go the 2025 controller firmware)." />;
  if (!s.helper.ready) return <Field label="Changing the controllers" description="Needs the Haversack Helper: install it from Device, Controllers, Reconnect help." />;
  if (s.tools.hhd) return <Field label="Changing the controllers" description="Handheld Daemon manages the controllers here, so Haversack only shows their settings." />;
  const current = s.current ?? {};
  const allowed = new Set(s.allowed);
  const apply = async (values: Record<string, unknown>) => {
    if (busy) return; // never disable a focused control: ignore a second press instead
    setBusy(true);
    try {
      setS(await controllerSettingsSet(values, keep));
    } catch (err) {
      toast(plainError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Field
        label="Change the controllers' own settings"
        description={
          s.tools.inputplumber
            ? "Applied at once. InputPlumber manages the button chords and touchpad haptics here, so those are left to it."
            : "Applied at once, through the Haversack Helper."
        }
      />
      <ToggleField label="Keep my changes" description="Apply them again whenever the controller reconnects or the device wakes." checked={keep} onChange={setKeep} />
      {Object.entries(CHOICES)
        .filter(([key]) => allowed.has(key) && current[key] !== undefined && !key.startsWith("led/"))
        .map(([key, c]) => (
          <DropdownItem
            key={key}
            label={c.label}
            rgOptions={c.options.map(([data, label]) => ({ data, label }))}
            selectedOption={current[key]}
            onChange={(o) => void apply({ [key]: o.data })}
          />
        ))}
      {Object.entries(TOGGLES)
        .filter(([key]) => allowed.has(key) && current[key] !== undefined && !key.startsWith("led/"))
        .map(([key, label]) => (
          <ToggleField key={key} label={label} checked={current[key] === "true"} onChange={(on) => void apply({ [key]: on ? "true" : "false" })} />
        ))}
      {(["left_handle/auto_sleep_time", "right_handle/auto_sleep_time"] as const)
        .filter((key) => current[key] !== undefined)
        .map((key) => (
          <DropdownItem
            key={key}
            label={key.startsWith("left") ? "Left controller sleeps after" : "Right controller sleeps after"}
            rgOptions={SLEEP.map(([data, label]) => ({ data, label }))}
            selectedOption={SLEEP.some(([v]) => v === current[key]) ? current[key] : null}
            onChange={(o) => void apply({ [key]: o.data })}
          />
        ))}
      {current["led/enabled"] !== undefined && (
        <>
          <Field label="Stick lights" />
          <ToggleField label="Lights on" checked={current["led/enabled"] === "true"} onChange={(on) => void apply({ "led/enabled": on ? "true" : "false", "led/mode": "custom" })} />
          <DropdownItem
            label="Effect"
            rgOptions={CHOICES["led/effect"].options.map(([data, label]) => ({ data, label }))}
            selectedOption={current["led/effect"]}
            onChange={(o) => void apply({ "led/mode": "custom", "led/effect": o.data })}
          />
          <SliderField
            label="Brightness"
            value={Number(current["led/brightness"] ?? 50)}
            min={0}
            max={100}
            step={5}
            showValue
            onChange={(v) => void apply({ "led/brightness": v })}
          />
          <SliderField label="Speed" value={Number(current["led/speed"] ?? 50)} min={0} max={100} step={5} showValue onChange={(v) => void apply({ "led/speed": v })} />
          {rgb &&
            (["Red", "Green", "Blue"] as const).map((name, i) => (
              <SliderField
                key={name}
                label={name}
                value={rgb[i]}
                min={0}
                max={100}
                step={5}
                showValue
                onChange={(v) => {
                  const next = [...rgb] as [number, number, number];
                  next[i] = v;
                  setRgb(next);
                }}
              />
            ))}
          {rgb && (
            <Field label="Colour" childrenLayout="inline">
              <DialogButton style={{ width: "auto" }} onClick={() => void apply({ "led/mode": "custom", "led/multi_intensity": rgb })}>
                Apply colour
              </DialogButton>
            </Field>
          )}
        </>
      )}
      {Object.keys(s.kept).length > 0 && (
        <Field label="Kept settings" description={`${Object.keys(s.kept).length} settings are applied again on reconnect.`}>
          <DialogButton
            onClick={() =>
              void controllerSettingsForget()
                .then(setS)
                .catch((err) => toast(plainError(err)))
            }
          >
            Forget them
          </DialogButton>
        </Field>
      )}
      {s.problem && <Field label="Last re-apply" description={s.problem} />}
    </>
  );
}
