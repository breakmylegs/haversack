import { DialogButton, Field, Focusable, SliderField, TextField, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { getSettings, setSetting, Settings } from "../backend";
import { CloudSection } from "./CloudSection";

export function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [name, setName] = useState("");

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s);
        setName(s.deviceName);
      })
      .catch((err) => toaster.toast({ title: "Keepsake", body: `Could not load settings: ${err}` }));
  }, []);

  const save = async (key: string, value: unknown, done: string) => {
    try {
      const updated = await setSetting(key, value);
      setSettings(updated);
      setName(updated.deviceName);
      toaster.toast({ title: "Keepsake", body: done });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not save: ${err}` });
    }
  };

  const locked = !settings || settings.readOnly;

  return (
    <div>
      {settings?.readOnly && (
        <Field
          label="Read-only safe mode"
          description="These settings were written by a newer Keepsake. Nothing can be changed until you update to that version or later."
        />
      )}
      <Field label="Device name" description="Shown on other devices next to snapshots from this one." childrenLayout="below">
        <TextField value={name} disabled={locked} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
        <DialogButton style={{ width: "auto" }} disabled={locked} onClick={() => void save("deviceName", name, "Device name saved.")}>
          Save
        </DialogButton>
      </Focusable>
      <ToggleField
        label="Include pre-releases"
        description="Offer beta versions as updates. Off means the Stable channel."
        checked={settings?.updateChannel === "prerelease"}
        disabled={locked}
        onChange={(on) => void save("updateChannel", on ? "prerelease" : "stable", on ? "Pre-release channel on." : "Stable channel on.")}
      />
      <Field
        label="Safety gates"
        description="Snapshots that remove or shrink too much are kept on this device instead of being uploaded. You can make these stricter, not looser."
      />
      <SliderField
        label="Refuse if more than this share of files disappear"
        value={settings?.gateMaxRemovedPercent ?? 50}
        min={5}
        max={50}
        step={5}
        showValue
        disabled={locked}
        onChange={(v) => void save("gateMaxRemovedPercent", v, `Limit set to ${v}%.`)}
      />
      <SliderField
        label="Refuse if the total size falls by more than"
        value={settings?.gateMaxSizeDropPercent ?? 70}
        min={5}
        max={70}
        step={5}
        showValue
        disabled={locked}
        onChange={(v) => void save("gateMaxSizeDropPercent", v, `Limit set to ${v}%.`)}
      />
      <SliderField
        label="Launch check timeout (seconds)"
        description="How long to wait for the cloud before starting the game with the local save."
        value={settings?.launchPullTimeout ?? 20}
        min={5}
        max={60}
        step={5}
        showValue
        disabled={locked}
        onChange={(v) => void save("launchPullTimeout", v, `Timeout set to ${v} seconds.`)}
      />
      <ToggleField
        label="Show a message after each save"
        checked={settings?.toastOnSync ?? true}
        disabled={locked}
        onChange={(on) => void save("toastOnSync", on, on ? "Save messages on." : "Save messages off.")}
      />
      {settings && <CloudSection settings={settings} onSettings={setSettings} />}
      {settings && <Field label="Device ID" description={settings.deviceId} />}
    </div>
  );
}
