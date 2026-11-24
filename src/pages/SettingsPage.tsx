import { DialogButton, Field, Focusable, TextField, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { getSettings, manifestStatus, ManifestStatus, refreshManifest, setSetting, Settings } from "../backend";
import { agoText, plainError } from "../format";
import { ModulesSection } from "./ModulesSection";
import { UpdatesPage } from "./UpdatesPage";

// Settings has a tab per part (layout v3, ADR-0073; the strip, ADR-0098).
export type SettingsPart = "general" | "modules" | "updates";

// Where games keep their saves, so a game update never replaces them (ADR-0098). The Ludusavi
// manifest is MIT licensed and credited wherever its data is used.
function GameDatabase() {
  const [status, setStatus] = useState<ManifestStatus | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    manifestStatus()
      .then(setStatus)
      .catch(() => undefined); // keep what is shown (v0.41.1)
  }, []);
  const refresh = async () => {
    setBusy(true);
    try {
      const result = await refreshManifest(true);
      toaster.toast({ title: "Haversack", body: result.ok ? "Game database updated." : "Could not update the game database." });
      setStatus(await manifestStatus());
    } catch (err) {
      toaster.toast({ title: "Haversack", body: `Could not update the game database: ${plainError(err)}` });
    } finally {
      setBusy(false);
    }
  };
  const found = status?.available
    ? `${status.games ?? 0} games, updated ${agoText(status.fetched)}.`
    : "Not downloaded yet. Haversack downloads it when it can reach GitHub.";
  return (
    <Field
      label="Game database"
      description={`Tells Haversack where each game keeps its saves, so an update sent to your other handheld never replaces them. ${found} ${status?.attribution ?? ""}`}
      childrenLayout="below"
    >
      <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void refresh()}>
        {busy ? "Updating" : "Update now"}
      </DialogButton>
    </Field>
  );
}

export function SettingsPage({ part = "general" }: { part?: SettingsPart }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [name, setName] = useState("");

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s);
        setName(s.deviceName);
      })
      .catch((err) => toaster.toast({ title: "Haversack", body: `Could not load settings: ${plainError(err)}` }));
  }, []);

  const save = async (key: string, value: unknown, done: string) => {
    try {
      const updated = await setSetting(key, value);
      setSettings(updated);
      setName(updated.deviceName);
      toaster.toast({ title: "Haversack", body: done });
    } catch (err) {
      toaster.toast({ title: "Haversack", body: `Could not save: ${plainError(err)}` });
    }
  };

  const locked = !settings || settings.readOnly;
  const safeMode = settings?.readOnly && (
    <Field
      label="Read-only safe mode"
      description="These settings were written by a newer Haversack. Nothing can be changed until you update to that version or later."
    />
  );

  if (part === "modules") return <div>{safeMode}<ModulesSection locked={locked} /></div>;
  if (part === "updates") {
    return (
      <div>
        {safeMode}
        <ToggleField
          label="Include pre-releases"
          description="Offer beta versions as updates. Off means the Stable channel."
          checked={settings?.updateChannel === "prerelease"}
          disabled={locked}
          onChange={(on) => void save("updateChannel", on ? "prerelease" : "stable", on ? "Pre-release channel on." : "Stable channel on.")}
        />
        <UpdatesPage />
      </div>
    );
  }
  if (part === "general") {
    return (
      <div>
        {safeMode}
        <Field label="Device name" description="Shown on your other devices when you pair and send games." childrenLayout="below">
          <TextField value={name} disabled={locked} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
          <DialogButton style={{ width: "auto" }} disabled={locked} onClick={() => void save("deviceName", name, "Device name saved.")}>
            Save
          </DialogButton>
        </Focusable>
        {settings && <Field label="Device ID" description={settings.deviceId} />}
        <GameDatabase />
      </div>
    );
  }

  return null;
}
