import { DialogButton, DropdownItem, Field, Focusable, Navigation, SliderField, TextField, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { getSettings, setSetting, Settings } from "../backend";
import { plainError } from "../format";
import { SETUP_PATH } from "../routes";
import { CloudSection } from "./CloudSection";
import { ModulesSection } from "./ModulesSection";
import { TidyCopies } from "./TidyCopies";
import { UpdatesPage } from "./UpdatesPage";

// Settings has a tab per part (layout v3, ADR-0073): what is everyone's, not one module's.
export type SettingsPart = "general" | "sync" | "cloud" | "modules" | "updates";

export function SettingsPage({ part = "general" }: { part?: SettingsPart }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [name, setName] = useState("");

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s);
        setName(s.deviceName);
      })
      .catch((err) => toaster.toast({ title: "Keepsake", body: `Could not load settings: ${plainError(err)}` }));
  }, []);

  const save = async (key: string, value: unknown, done: string) => {
    try {
      const updated = await setSetting(key, value);
      setSettings(updated);
      setName(updated.deviceName);
      toaster.toast({ title: "Keepsake", body: done });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not save: ${plainError(err)}` });
    }
  };

  const locked = !settings || settings.readOnly;
  const safeMode = settings?.readOnly && (
    <Field
      label="Read-only safe mode"
      description="These settings were written by a newer Keepsake. Nothing can be changed until you update to that version or later."
    />
  );

  if (part === "cloud") return <div>{safeMode}{settings && <CloudSection settings={settings} onSettings={setSettings} />}</div>;
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
        <Field label="Device name" description="Shown on other devices next to snapshots from this one." childrenLayout="below">
          <TextField value={name} disabled={locked} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Focusable style={{ display: "flex", gap: 8, margin: "8px 0" }}>
          <DialogButton style={{ width: "auto" }} disabled={locked} onClick={() => void save("deviceName", name, "Device name saved.")}>
            Save
          </DialogButton>
        </Focusable>
        <Field label="Setup" description="Walk through device name, sign-in, scanning and choosing games again." childrenLayout="inline">
          <DialogButton style={{ width: "auto" }} disabled={locked} onClick={() => Navigation.Navigate(SETUP_PATH)}>
            Run setup again
          </DialogButton>
        </Field>
        {settings && <Field label="Device ID" description={settings.deviceId} />}
      </div>
    );
  }

  return (
    <div>
      {safeMode}
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
      <SliderField
        label="Background sync every (minutes)"
        description="How often Keepsake downloads newer cloud saves ahead of time and saves changes made outside a game session."
        value={settings?.idleSyncMinutes ?? 30}
        min={10}
        max={240}
        step={10}
        showValue
        disabled={locked}
        onChange={(v) => void save("idleSyncMinutes", v, `Background sync every ${v} minutes.`)}
      />
      <ToggleField
        label="Show a message after each save"
        checked={settings?.toastOnSync ?? true}
        disabled={locked}
        onChange={(on) => void save("toastOnSync", on, on ? "Save messages on." : "Save messages off.")}
      />
      <ToggleField
        label="Sync Steam games that Steam Cloud does not back up"
        description="A Steam game you have played with no Steam Cloud saves starts syncing on its own, like your non-Steam games. Games that use Steam Cloud stay off unless you turn them on. A game you turn off stays off."
        checked={settings?.steamAutoSync ?? true}
        disabled={locked || !(settings?.steamCloudDetection ?? true)}
        onChange={(on) => void save("steamAutoSync", on, on ? "Steam games without Steam Cloud sync automatically." : "Steam games only sync when you turn them on.")}
      />
      <DropdownItem
        label="When saves differ"
        description="Ask me: you choose every time (the default). Take the newest: Keepsake keeps the newer version by itself when exactly two versions differ, their times are far enough apart and no clock looks wrong; the other version stays in History with Undo."
        rgOptions={[
          { data: "ask", label: "Ask me" },
          { data: "newest", label: "Take the newest" },
        ]}
        selectedOption={settings?.conflictPolicy ?? "ask"}
        disabled={locked}
        onChange={(o) => void save("conflictPolicy", o.data, o.data === "newest" ? "Keepsake now takes the newest save when it can be sure." : "Keepsake asks you whenever saves differ.")}
      />
      <TidyCopies />
      <ToggleField
        label="Registry keys"
        description="Allow games to sync the Proton registry keys their manifest entry lists. Each game still has to turn it on."
        checked={settings?.registrySync ?? true}
        disabled={locked}
        onChange={(on) => void save("registrySync", on, on ? "Registry sync available." : "Registry sync off for all games.")}
      />
      <ToggleField
        label="Detect Steam Cloud"
        description="Label Steam games that use Steam Cloud, and offer to sync the ones that do not."
        checked={settings?.steamCloudDetection ?? true}
        disabled={locked}
        onChange={(on) => void save("steamCloudDetection", on, on ? "Steam Cloud detection on." : "Steam Cloud detection off.")}
      />
      <ToggleField
        label="Snapshot when the device sleeps"
        description="Save a snapshot of a running game when the device goes to sleep. Your other device is told about it but never uses it unless you restore it from History."
        checked={settings?.suspendSnapshots ?? false}
        disabled={locked}
        onChange={(on) => void save("suspendSnapshots", on, on ? "Sleep snapshots on." : "Sleep snapshots off.")}
      />
      <ToggleField
        label="Show other launchers"
        description="List Heroic, Lutris and Bottles games and emulator saves in Games. Each one still syncs only when you turn it on."
        checked={settings?.otherLaunchers ?? true}
        disabled={locked}
        onChange={(on) => void save("otherLaunchers", on, on ? "Other launchers shown. Rescan Games to see them." : "Other launchers hidden.")}
      />
    </div>
  );
}
