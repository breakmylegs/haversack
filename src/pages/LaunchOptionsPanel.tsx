import { DialogButton, Field, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { launchApply, launchPresets, LaunchPresets, launchRestore } from "../backend";
import { plainError } from "../format";

// A game's launch option presets (R29 stage 5, ADR-0097): Proton's own settings, switched on or off.
// Steam is changed only through SteamClient after a button press, the options as they were are kept
// first, and the result is read back (P15). Verified in @decky/ui: AppDetails.strLaunchOptions,
// SteamClient.Apps.RegisterForAppDetails and SetAppLaunchOptions (assumption A65).

/** Steam's launch options for ``appid``, loading the game's details if Steam has not yet; null if unknown. */
function readOptions(appid: number): Promise<string | null> {
  const now = appDetailsStore?.GetAppDetails(appid)?.strLaunchOptions;
  if (typeof now === "string") return Promise.resolve(now);
  return new Promise((resolve) => {
    let done = false;
    const ref: { handle?: { unregister: () => void } } = {}; // a callback may come before the handle is set
    const finish = (value: string | null) => {
      if (done) return;
      done = true;
      ref.handle?.unregister();
      resolve(value);
    };
    ref.handle = SteamClient.Apps.RegisterForAppDetails(appid, (data) => finish(typeof data?.strLaunchOptions === "string" ? data.strLaunchOptions : null));
    if (done) ref.handle?.unregister(); // answered at once: unregister now that the handle exists
    window.setTimeout(() => finish(appDetailsStore?.GetAppDetails(appid)?.strLaunchOptions ?? null), 3000);
  });
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

async function setAndCheck(appid: number, options: string): Promise<boolean> {
  SteamClient.Apps.SetAppLaunchOptions(appid, options);
  await sleep(500);
  return (await readOptions(appid)) === options;
}

export function LaunchOptionsPanel({ gameKey, appid }: { gameKey: string; appid: number }) {
  const [state, setState] = useState<LaunchPresets | null>(null);
  const [unknown, setUnknown] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const current = await readOptions(appid);
    if (current === null) {
      setUnknown(true);
      return;
    }
    setUnknown(false);
    setState(await launchPresets(gameKey, current));
  };
  useEffect(() => {
    load().catch(() => undefined); // keep what is shown (v0.41.1)
  }, [gameKey, appid]);

  const run = async (get: (current: string) => Promise<{ appid: number; options: string }>, done: string) => {
    if (busy) return; // never disable a focused control: ignore a second press
    setBusy(true);
    try {
      const current = await readOptions(appid);
      if (current === null) throw new Error("Steam has not loaded this game's details yet; open its page in the library once");
      const next = await get(current);
      const ok = await setAndCheck(next.appid, next.options);
      toaster.toast({ title: "Haversack", body: ok ? done : "Steam did not keep the new launch options. Nothing else was changed." });
      await load();
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };

  if (unknown) return <Field label="Launch options" description="Steam has not loaded this game's details yet. Open its page in the library once, then come back." />;
  if (!state) return null;
  if (state.strict) return <Field label="Launch options" description="This game uses the strict launch gate, which manages its launch options. Turn the gate off to use these presets." />;
  if (state.problem) return <Field label="Launch options" description={state.problem} />;
  const toggle = (id: string, on: boolean) => {
    const wanted = state.presets.filter((p) => (p.id === id ? on : p.on)).map((p) => p.id);
    void run((current) => launchApply(gameKey, current, wanted), "Launch options changed. They apply the next time the game starts.");
  };
  return (
    <>
      <Field label="Launch options" description={state.options ? `Now: ${state.options}` : "Now: none."} />
      {state.presets.map((p) => (
        <ToggleField key={p.id} label={p.label} description={`${p.about} (${p.var}=1)`} checked={p.on} onChange={(on) => toggle(p.id, on)} />
      ))}
      {state.original !== null && (
        <Field description={`Before Haversack changed them: ${state.original || "none"}.`}>
          <DialogButton onClick={() => void run(() => launchRestore(gameKey), "Launch options put back as they were.")}>Put back original</DialogButton>
        </Field>
      )}
    </>
  );
}
