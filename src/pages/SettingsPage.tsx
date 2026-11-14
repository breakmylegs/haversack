import { DialogButton, Field, Focusable, TextField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { getSettings, setSetting, Settings } from "../backend";

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

  const save = async () => {
    try {
      const updated = await setSetting("deviceName", name);
      setSettings(updated);
      setName(updated.deviceName);
      toaster.toast({ title: "Keepsake", body: "Device name saved." });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not save: ${err}` });
    }
  };

  return (
    <div>
      <Field label="Device name" description="Shown on other devices next to snapshots from this one." childrenLayout="below">
        <TextField value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
        <DialogButton style={{ width: "auto" }} disabled={!settings} onClick={() => void save()}>
          Save
        </DialogButton>
      </Focusable>
      {settings && <Field label="Device ID" description={settings.deviceId} />}
    </div>
  );
}
