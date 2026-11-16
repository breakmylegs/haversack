import { DialogButton, DropdownItem, Field, Focusable, Navigation, TextField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  advisorRedetect,
  advisorRefresh,
  advisorSelectGame,
  advisorSettings,
  advisorView,
  AdvisorRecommendation,
  AdvisorView,
  discoverGames,
  GameEntry,
} from "../backend";

// Advisor is read-only (P16, ADR-0019): this page shows advice and copies text. It never changes a setting.

const ADVISOR_EVENT = "keepsake_advisor";
const WORKLOADS = ["light", "medium", "heavy"] as const;
const WORKLOAD_LABELS: Record<(typeof WORKLOADS)[number], string> = {
  light: "Light (60 fps)",
  medium: "Medium (45 fps)",
  heavy: "Heavy (30 fps)",
};
const CONFIDENCE_COLOURS = { high: "#59bf40", medium: "#e5b33a", low: "#9aa0a6" };
const MAPPING_TEXT = {
  steam: "Steam game",
  manifest: "Shortcut, matched to its Steam app through the save manifest",
  manual: "Shortcut, matched to the Steam app ID you entered",
  name: "Shortcut with no Steam app ID: looked up by name, so advice is less certain",
};
const SECTION_TITLES: [keyof AdvisorRecommendation["lines"], string][] = [
  ["power", "Power"],
  ["display", "Display"],
  ["scaling", "Resolution and scaling"],
  ["frame_gen", "Frame generation"],
  ["in_game", "In game"],
  ["battery", "Battery"],
];

// The Steam client has no clipboard API (A142); CEF's navigator.clipboard is tried, and the text is always shown.
async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    toaster.toast({ title: "Keepsake", body: "Copied." });
  } catch {
    toaster.toast({ title: "Keepsake", body: "Copy is not available here. The text is shown so you can type it." });
  }
}

function Recommendation({ rec }: { rec: AdvisorRecommendation }) {
  const from =
    rec.source === "fallback"
      ? "General advice for this device"
      : `Deck Verified report from ${rec.device_reported || "an unnamed device"} (${rec.matchLabel})`;
  return (
    <Field
      label={from}
      description={
        <span>
          <span style={{ color: CONFIDENCE_COLOURS[rec.confidence] }}>{"●"} </span>
          {`${rec.confidence} confidence`}
          {rec.report_date ? `, ${rec.report_date.slice(0, 10)}` : ""}
          {rec.votes ? `, ${rec.votes} votes` : ""}
        </span>
      }
      childrenLayout="below"
    >
      <div style={{ fontSize: 13 }}>
        {SECTION_TITLES.filter(([key]) => (rec.lines[key] ?? []).length > 0).map(([key, title]) => (
          <div key={key} style={{ marginBottom: 4 }}>
            <b>{title}: </b>
            {rec.lines[key].join(" ")}
          </div>
        ))}
        {rec.flags.map((flag) => (
          <div key={flag} style={{ color: "#e5b33a" }}>
            {flag}
          </div>
        ))}
        {rec.notes && <div style={{ opacity: 0.8 }}>{rec.notes}</div>}
        {rec.compat.launch_options && (
          <div style={{ marginTop: 4 }}>
            Launch options from the report: <code>{rec.compat.launch_options}</code>
          </div>
        )}
      </div>
      <Focusable style={{ display: "flex", gap: 8, marginTop: 4 }}>
        {rec.compat.launch_options && (
          <DialogButton style={{ width: "auto" }} onClick={() => void copyText(rec.compat.launch_options ?? "")}>
            Copy launch options
          </DialogButton>
        )}
        {rec.source_url && (
          <DialogButton style={{ width: "auto" }} onClick={() => Navigation.NavigateToExternalWeb(rec.source_url)}>
            Open the report
          </DialogButton>
        )}
      </Focusable>
    </Field>
  );
}

export function AdvisorPage() {
  const [view, setView] = useState<AdvisorView | null>(null);
  const [busy, setBusy] = useState(false);
  const [games, setGames] = useState<GameEntry[] | null>(null);
  const [steamId, setSteamId] = useState("");

  const act = async (work: () => Promise<AdvisorView>) => {
    setBusy(true);
    try {
      setView(await work());
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void act(advisorView);
    const listener = addEventListener(ADVISOR_EVENT, () => void advisorView().then(setView).catch(() => undefined));
    return () => removeEventListener(ADVISOR_EVENT, listener);
  }, []);

  if (view && !view.running) return <Field label="Advisor is off" description="Switch it on in Settings, Modules." />;
  if (!view?.device || !view.settings) return <Field label="Loading the Advisor" />;
  const { device, settings, stack, game } = view;

  const chooseGame = async () => {
    try {
      const found = await discoverGames(false);
      setGames(found.games);
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Could not list games: ${err}` });
    }
  };

  const saveSteamId = () => {
    const id = Number(steamId.trim());
    if (!game || !Number.isInteger(id) || id <= 0) {
      toaster.toast({ title: "Keepsake", body: "Enter the game's Steam app ID, a whole number." });
      return;
    }
    void act(() => advisorSettings({ steamIdOverrides: { ...settings.steamIdOverrides, [String(game.appid)]: id } }));
  };

  return (
    <div>
      <Field
        label={`Device: ${device.name}`}
        description={`${device.apu}. ${device.how === "generic" ? "Not in the registry, so advice is general. Choose your device below." : device.how === "override" ? "Chosen by you." : device.verified ? "Detected." : "Detected; the profile is waiting for a check on this device."}`}
      />
      <DropdownItem
        label="This device is"
        rgOptions={[{ data: "", label: "Detect automatically" }, ...(view.devices ?? []).map((d) => ({ data: d.id, label: d.name }))]}
        selectedOption={settings.deviceOverride}
        disabled={busy}
        onChange={(option) => void act(() => advisorSettings({ deviceOverride: option.data }))}
      />
      <DropdownItem
        label="How demanding is the game?"
        rgOptions={WORKLOADS.map((w) => ({ data: w, label: WORKLOAD_LABELS[w] }))}
        selectedOption={settings.workload}
        disabled={busy}
        onChange={(option) => void act(() => advisorSettings({ workload: option.data }))}
      />
      {stack && (
        <Field
          label="Tuning tools"
          description={
            stack.detected.length
              ? stack.detected.map((t) => `${stack.names[t.id] ?? t.id}${t.disabled ? " (disabled)" : ""}`).join(", ")
              : "None found besides Steam's own controls."
          }
        />
      )}
      {(view.conflicts ?? []).map((c) => (
        <Field key={c.kind} label="Tool conflict" description={c.text} />
      ))}

      <Field
        label={game ? `Advice for ${game.name || `app ${game.appid}`}` : "No game chosen"}
        description={
          game
            ? MAPPING_TEXT[game.mapping]
            : "Start a game, or choose one here. Until then this is general advice for your device."
        }
        childrenLayout="below"
      >
        <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void chooseGame()}>
            Choose a game
          </DialogButton>
          <DialogButton style={{ width: "auto" }} disabled={busy || !game} onClick={() => void act(advisorRefresh)}>
            Refresh reports
          </DialogButton>
          <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void act(advisorRedetect)}>
            Detect device and tools again
          </DialogButton>
        </Focusable>
      </Field>
      {games && (
        <Field label="Choose a game" childrenLayout="below">
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {games.map((g) => (
              <DialogButton
                key={g.key}
                style={{ width: "auto" }}
                disabled={busy}
                onClick={() => {
                  setGames(null);
                  void act(() => advisorSelectGame(g.appid));
                }}
              >
                {g.name}
              </DialogButton>
            ))}
          </Focusable>
        </Field>
      )}
      {game?.shortcut && (
        <Field
          label="Steam app ID for this shortcut"
          description="Optional. If the game is also on Steam, enter its app ID (from its store page address) for better matches."
          childrenLayout="below"
        >
          <TextField value={steamId} disabled={busy} onChange={(e) => setSteamId(e.target.value)} />
          <DialogButton style={{ width: "auto", marginTop: 4 }} disabled={busy || !steamId.trim()} onClick={saveSteamId}>
            Use this app ID
          </DialogButton>
        </Field>
      )}
      {view.anticheat?.entry && (
        <Field
          label={`Anti-cheat: ${view.anticheat.entry.status}`}
          description={`${view.anticheat.entry.meaning}${view.anticheat.entry.blocked ? " Settings cannot help online play." : ""}`}
        />
      )}
      {view.source?.error && <Field label="Community reports" description={view.source.error} />}
      {(view.recommendations ?? []).map((rec, i) => (
        <Recommendation key={`${rec.source}-${rec.source_url}-${i}`} rec={rec} />
      ))}
      <Field label="Sources" description={(view.attribution ?? []).join(" ")} />
    </div>
  );
}
