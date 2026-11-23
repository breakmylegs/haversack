import { ConfirmModal, DialogButton, Field, Focusable, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { GameConfig, strictUnwrap, strictWrap, updateGameConfig } from "../backend";
import { plainError } from "../format";

type Mode = GameConfig["launchGate"];

const MODES: Record<Mode, string> = {
  freeze: "Freeze (default): the game is paused for a moment at launch while the cloud is checked.",
  strict: "Strict launch gate: the game waits for the check before it starts. Changes this game's launch options.",
  off: "Off: the cloud is checked at launch but a newer save is only loaded after you quit.",
};

function currentLaunchOptions(appid: number): string {
  // Verified in @decky/ui: AppDetails.strLaunchOptions via appDetailsStore (assumption A65).
  return appDetailsStore?.GetAppDetails(appid)?.strLaunchOptions ?? "";
}

export function LaunchGatePanel({ gameKey, appid, mode, onMode }: { gameKey: string; appid: number; mode: Mode; onMode: (m: Mode) => void }) {
  const toStrict = () =>
    showModal(
      <ConfirmModal
        strTitle="Use the strict launch gate?"
        strDescription="Haversack will add its gate in front of this game's launch command and keep your existing launch options. Turning it off puts your original launch options back exactly."
        strOKButtonText="Use strict gate"
        strCancelButtonText="Cancel"
        onOK={async () => {
          try {
            const result = await strictWrap(gameKey, currentLaunchOptions(appid));
            SteamClient.Apps.SetAppLaunchOptions(result.appid, result.options);
            onMode("strict");
            toaster.toast({ title: "Haversack", body: "Strict launch gate on." });
          } catch (err) {
            toaster.toast({ title: "Haversack", body: `Not changed: ${plainError(err)}` });
          }
        }}
      />,
    );

  const choose = async (next: Mode): Promise<void> => {
    if (next === mode) return;
    if (next === "strict") {
      toStrict();
      return;
    }
    try {
      if (mode === "strict") {
        const result = await strictUnwrap(gameKey, next);
        SteamClient.Apps.SetAppLaunchOptions(result.appid, result.options);
      } else {
        await updateGameConfig(gameKey, { launchGate: next });
      }
      onMode(next);
    } catch (err) {
      toaster.toast({ title: "Haversack", body: `Not changed: ${plainError(err)}` });
    }
  };

  return (
    <Field label="Launch gate" description={MODES[mode]} childrenLayout="below">
      <Focusable style={{ display: "flex", gap: 8 }}>
        {(Object.keys(MODES) as Mode[]).map((m) => (
          <DialogButton key={m} style={{ width: "auto", opacity: m === mode ? 1 : 0.6 }} onClick={() => void choose(m)}>
            {m === "freeze" ? "Freeze" : m === "strict" ? "Strict" : "Off"}
          </DialogButton>
        ))}
      </Focusable>
    </Field>
  );
}
