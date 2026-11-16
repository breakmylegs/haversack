import { DialogButton, DropdownItem, Field, Focusable, Navigation, TextField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  advisorAiGenerate,
  advisorAiModels,
  advisorRedetect,
  advisorRefresh,
  advisorSelectGame,
  advisorSettings,
  advisorView,
  AdvisorRecommendation,
  AdvisorView,
  discoverGames,
  GameEntry,
  saveAiKey,
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
        {rec.launch && (
          <div style={{ marginTop: 4 }}>
            <div>
              Launch options: <code>{rec.launch.recommended}</code>
            </div>
            {rec.launch.sameAsCurrent && <div>These match what you already have.</div>}
            {rec.launch.merged && (
              <div>
                Combined with yours: <code>{rec.launch.merged}</code> {rec.launch.mergeNotes.join(" ")}
              </div>
            )}
            {rec.launch.flags.map((flag) => (
              <div key={flag} style={{ color: "#e5b33a" }}>
                {flag}
              </div>
            ))}
            <div style={{ opacity: 0.8 }}>Set them yourself in {rec.launch.where}.</div>
          </div>
        )}
      </div>
      <Focusable style={{ display: "flex", gap: 8, marginTop: 4 }}>
        {rec.launch && !rec.launch.sameAsCurrent && (
          <DialogButton style={{ width: "auto" }} onClick={() => void copyText(rec.launch?.recommended ?? "")}>
            Copy launch options
          </DialogButton>
        )}
        {rec.launch?.merged && (
          <DialogButton style={{ width: "auto" }} onClick={() => void copyText(rec.launch?.merged ?? "")}>
            Copy combined
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

// Optional AI advice (P18): off until a provider is chosen and its key added. Asked only from the button, shown
// as unverified, never acted on. The key goes to Keepsake's backend secrets and never comes back to this page.
function AiSection({ view, busy, act }: { view: AdvisorView; busy: boolean; act: (work: () => Promise<AdvisorView>) => Promise<void> }) {
  const [key, setKey] = useState("");
  const [models, setModels] = useState<{ id: string; label: string }[]>([]);
  const settings = view.settings;
  const ai = view.ai;
  if (!settings || !ai) return null;
  const provider = ai.providers.find((p) => p.id === settings.aiProvider);

  const saveKey = async () => {
    if (!provider) return;
    try {
      await saveAiKey(provider.id, { apiKey: key.trim() });
      setKey("");
      await act(advisorView);
      toaster.toast({ title: "Keepsake", body: `${provider.name} key saved.` });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    }
  };

  const loadModels = async () => {
    if (!provider) return;
    try {
      setModels(await advisorAiModels(provider.id));
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    }
  };

  return (
    <>
      <DropdownItem
        label="AI advice (optional)"
        description="Uses your own key. Sends only the game's title, your device's hardware, your tools and the settings shown above."
        rgOptions={[{ data: "", label: "Off" }, ...ai.providers.map((p) => ({ data: p.id, label: p.name }))]}
        selectedOption={settings.aiProvider}
        disabled={busy}
        onChange={(option) => void act(() => advisorSettings({ aiProvider: option.data }))}
      />
      {provider && !provider.keySet && (
        <Field label={`${provider.name} API key`} childrenLayout="below">
          <TextField value={key} bIsPassword disabled={busy} onChange={(e) => setKey(e.target.value)} />
          <DialogButton style={{ width: "auto", marginTop: 4 }} disabled={busy || !key.trim()} onClick={() => void saveKey()}>
            Save key
          </DialogButton>
        </Field>
      )}
      {provider?.keySet && (
        <>
          <Focusable style={{ display: "flex", gap: 8, margin: "4px 0" }}>
            <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void loadModels()}>
              Load models
            </DialogButton>
            <DialogButton
              style={{ width: "auto" }}
              disabled={busy || !settings.aiModel || !view.game}
              onClick={() => void act(advisorAiGenerate)}
            >
              Ask {provider.name}
            </DialogButton>
          </Focusable>
          {models.length > 0 && (
            <DropdownItem
              label="Model"
              rgOptions={models.map((m) => ({ data: m.id, label: m.label }))}
              selectedOption={settings.aiModel}
              disabled={busy}
              onChange={(option) => void act(() => advisorSettings({ aiModel: option.data }))}
            />
          )}
          <Field
            label={settings.aiModel ? `Model: ${settings.aiModel}` : "No model chosen yet"}
            description={`${ai.usedToday} of ${settings.aiDailyCap || "unlimited"} requests used today.`}
          />
        </>
      )}
      {ai.result?.error && <Field label="AI advice" description={ai.result.error} />}
      {ai.result?.rec && (
        <>
          <Field
            label={`${ai.result.label}: ${ai.result.provider}, ${ai.result.model}`}
            description={ai.result.discarded.length ? `Left out because they did not fit: ${ai.result.discarded.join("; ")}.` : "Checked against your device."}
          />
          <Recommendation rec={ai.result.rec} />
        </>
      )}
    </>
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
      {view.proton && (
        <Field
          label={`Proton: ${view.proton.recommended}${view.proton.matches ? " (already set)" : ""}`}
          description={`${view.proton.signalText}${view.proton.asReported ? ` Reported as ${view.proton.asReported}.` : ""} You have ${view.proton.current}. ${view.proton.matches ? "" : `To change it: ${view.proton.where}.`} ${view.proton.installNote ?? ""} ${view.proton.peer}`}
        />
      )}
      {view.current?.power && (
        <Field
          label={`Your ${view.stack?.names[view.current.power.tool] ?? view.current.power.tool} setting: ${view.current.power.tdp_w ?? "off"}${view.current.power.tdp_w ? " W" : ""}`}
          description={`From its ${view.current.power.scope}.${view.current.power.note ? ` ${view.current.power.note}` : ""}`}
        />
      )}
      {view.current?.framegen && (
        <Field
          label={`Your lsfg-vk profile: ${view.current.framegen.profile ?? "none for this game"}`}
          description={view.current.framegen.multiplier ? `Multiplier ${view.current.framegen.multiplier}x.` : "No frame generation set for this game."}
        />
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
      <AiSection view={view} busy={busy} act={act} />
      <Field label="Sources" description={(view.attribution ?? []).join(" ")} />
    </div>
  );
}
