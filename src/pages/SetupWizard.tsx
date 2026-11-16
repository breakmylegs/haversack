import { DialogButton, Field, Focusable, Navigation, TextField, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  approveMatch,
  discoverGames,
  finishSetup,
  GameMatch,
  getSettings,
  matchGames,
  PlanEntry,
  planSync,
  rejectMatch,
  setSetting,
  Settings,
} from "../backend";
import { PLAN_LABELS } from "../format";
import { ROUTE_PATH } from "../routes";
import { CloudSection } from "./CloudSection";

const STEPS = ["Device name", "Cloud", "Scan games", "Review matches", "Choose games", "Dry run", "Confirm"];

function matchLine(m: GameMatch): string {
  if (m.proposal) return `Looks like ${m.proposal.candidate.title ?? m.proposal.candidate.gameKey}. Approve or reject it.`;
  if (m.gameKey) return m.title ? `Matched: ${m.title}` : `Own game key: ${m.gameKey}`;
  return "No match yet. You can match it later on its game page.";
}

// Gaming Mode's footer bar (Steam menu, Select and Back hints) overlays the bottom of full-screen pages.
const FOOTER_CLEARANCE = 96;

export function SetupWizard() {
  const [step, setStep] = useState(0);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [name, setName] = useState("");
  const [matches, setMatches] = useState<GameMatch[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [plan, setPlan] = useState<PlanEntry[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getSettings()
      .then((s) => {
        setSettings(s);
        setName(s.deviceName);
      })
      .catch((err) => toaster.toast({ title: "Keepsake", body: `Could not load settings: ${err}` }));
  }, []);

  const work = async (task: () => Promise<void>) => {
    setBusy(true);
    try {
      await task();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const loadMatches = async () => {
    const list = await matchGames();
    setMatches(list.filter((m) => m.kind === "shortcut" || settings?.showSteamApps));
  };

  const leave = () => {
    Navigation.Navigate(`${ROUTE_PATH}/games`);
  };

  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));
  const syncable = (matches ?? []).filter((m) => m.gameKey && !m.proposal);

  // Back, Continue and Skip: under the step title, so they never need scrolling and controller focus reaches
  // them first, and again at the end of the step (A154).
  const nav = (
    <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "16px 0" }}>
      {step > 0 && (
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={back}>
          Back
        </DialogButton>
      )}
      {step === 0 && (
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy || !settings || settings.readOnly}
          onClick={() =>
            void work(async () => {
              setSettings(await setSetting("deviceName", name));
              next();
            })
          }
        >
          Save and continue
        </DialogButton>
      )}
      {(step === 1 || step === 3 || (step === 2 && matches !== null)) && (
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={next}>
          Continue
        </DialogButton>
      )}
      {step === 4 && (
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() =>
            void work(async () => {
              setPlan(await planSync(chosen));
              next();
            })
          }
        >
          Show the plan
        </DialogButton>
      )}
      {step === 5 && (
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={next}>
          Continue
        </DialogButton>
      )}
      {step === 6 && (
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() =>
            void work(async () => {
              const result = await finishSetup(chosen);
              toaster.toast({ title: "Keepsake", body: `Setup finished. Syncing ${result.enabled} games.` });
              leave();
            })
          }
        >
          Finish setup
        </DialogButton>
      )}
      <DialogButton
        style={{ width: "auto" }}
        disabled={busy}
        onClick={() =>
          void work(async () => {
            await setSetting("setupComplete", true);
            leave();
          })
        }
      >
        Skip setup
      </DialogButton>
    </Focusable>
  );

  return (
    // The same top clearance as Decky's own full-screen pages; the bottom padding clears Gaming Mode's footer bar.
    <div
      style={{ marginTop: 40, padding: `0 24px ${FOOTER_CLEARANCE}px`, height: "calc(100% - 40px)", overflowY: "auto", boxSizing: "border-box" }}
    >
      <Field label={`Set up Keepsake: step ${step + 1} of ${STEPS.length}, ${STEPS[step]}`} />
      {nav}

      {step === 0 && (
        <>
          <Field label="Name this device" description="Other devices show this name next to its saves." childrenLayout="below">
            <TextField value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
        </>
      )}

      {step === 1 && settings && (
        <>
          <Field description="Choose OneDrive and sign in with your phone using the code or QR code. You can stay on the test store and sign in later, but saves then stay on this device." />
          <CloudSection settings={settings} onSettings={setSettings} />
        </>
      )}

      {step === 2 && (
        <Field
          label={matches ? `${matches.length} games found` : "Find the games on this device"}
          description={
            settings?.showSteamApps
              ? "Non-Steam shortcuts and Steam games are listed."
              : "Non-Steam shortcuts are listed. Steam games are hidden because Steam Cloud usually covers them (Settings can show them)."
          }
          childrenLayout="below"
        >
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() =>
              void work(async () => {
                await discoverGames(true);
                await loadMatches();
              })
            }
          >
            {busy ? "Scanning" : "Scan games"}
          </DialogButton>
        </Field>
      )}

      {step === 3 &&
        (matches ?? []).map((m) => (
          <Field key={m.key} label={m.name} description={matchLine(m)} childrenLayout="below">
            {m.proposal && (
              <Focusable style={{ display: "flex", gap: 8 }}>
                <DialogButton
                  style={{ width: "auto" }}
                  disabled={busy}
                  onClick={() => void work(async () => (await approveMatch(m.key), await loadMatches()))}
                >
                  Approve
                </DialogButton>
                <DialogButton
                  style={{ width: "auto" }}
                  disabled={busy}
                  onClick={() => void work(async () => (await rejectMatch(m.key), await loadMatches()))}
                >
                  Not this game
                </DialogButton>
              </Focusable>
            )}
          </Field>
        ))}

      {step === 4 && (
        <>
          <Field
            description={
              syncable.length
                ? "Choose the games to keep in step between your devices. You can change this later on each game's page."
                : "No matched games yet. Go back to scan or match games, or finish and set games up later."
            }
          />
          {syncable.map((m) => (
            <ToggleField
              key={m.key}
              label={m.name}
              description={m.title ?? m.gameKey ?? ""}
              checked={chosen.includes(m.key) || m.enabled}
              disabled={m.enabled}
              onChange={(on) => setChosen((c) => (on ? [...c, m.key] : c.filter((k) => k !== m.key)))}
            />
          ))}
        </>
      )}

      {step === 5 && (
        <>
          <Field
            label="What the first sync will do"
            description="Nothing has changed yet. Conflicts are never resolved for you: you will choose which save to keep."
          />
          {(plan ?? []).map((p) => (
            <Field key={p.key} label={p.name} description={`${PLAN_LABELS[p.action]}${p.action === "error" && p.reason ? `: ${p.reason}` : ""}`} />
          ))}
          {plan && plan.length === 0 && <Field label="No games chosen" />}
        </>
      )}

      {step === 6 && (
        <Field
          label={`Turn on sync for ${chosen.length} games`}
          description="Keepsake then checks the cloud before each launch and saves after each exit. A first sync starts now."
        />
      )}

      {nav}
    </div>
  );
}
