import { DialogButton, Field, Focusable } from "@decky/ui";
import { useState } from "react";
import {
  exportDiagnostics,
  getEnvironment,
  getGameProcesses,
  getSteamProbe,
  httpsTest,
  steamOpsList,
  steamProbe,
} from "../backend";
import { deckyMechanisms, runningAppDetails } from "../probes";
import { plainError } from "../format";
import { JsonBlock } from "./JsonBlock";
import { NavigationRecorder } from "./NavigationRecorder";

type Section = "environment" | "steam" | "processes" | "frontend" | "https" | "steamops" | "export";

export function DiagnosticsPage() {
  const [results, setResults] = useState<Partial<Record<Section, unknown>>>({});
  const [busy, setBusy] = useState<Section | null>(null);

  const run = async (section: Section, work: () => Promise<unknown>) => {
    setBusy(section);
    try {
      const value = await work();
      setResults((prev) => ({ ...prev, [section]: value }));
    } catch (err) {
      setResults((prev) => ({ ...prev, [section]: { error: plainError(err) } }));
    } finally {
      setBusy(null);
    }
  };

  const runningAppId = (): number | undefined => SteamUIStore?.MainRunningAppID ?? undefined;

  const frontendFacts = () => ({ decky: deckyMechanisms(), running: runningAppDetails() });

  return (
    <div>
      <Field
        label="Diagnostics"
        description="Facts about this device for troubleshooting. The export is saved in Haversack's settings folder on this device."
      />
      <NavigationRecorder />
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "8px 0" }}>
        <DialogButton style={{ width: "auto" }} disabled={!!busy} onClick={() => run("environment", getEnvironment)}>
          Environment
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={!!busy} onClick={() => run("steam", getSteamProbe)}>
          Steam shortcuts
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          disabled={!!busy}
          onClick={() =>
            run("processes", async () => {
              const appid = runningAppId();
              return appid ? { appid, processes: await getGameProcesses(appid) } : { note: "No game is running." };
            })
          }
        >
          Game processes
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={!!busy} onClick={() => run("frontend", async () => frontendFacts())}>
          Frontend facts
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={!!busy} onClick={() => run("https", httpsTest)}>
          Test HTTPS
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          disabled={!!busy}
          onClick={() =>
            run("steamops", async () => {
              await steamProbe();
              await new Promise((resolve) => setTimeout(resolve, 1500));
              return (await steamOpsList()).slice(0, 5);
            })
          }
        >
          Probe Steam APIs
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          disabled={!!busy}
          onClick={() => run("export", async () => ({ file: await exportDiagnostics(frontendFacts()) }))}
        >
          Export diagnostics
        </DialogButton>
      </Focusable>
      {busy && <Field label="Working" description={`Running ${busy}.`} />}
      {(Object.keys(results) as Section[]).map((section) => (
        <Field key={section} label={section} childrenLayout="below">
          <JsonBlock value={results[section]} />
        </Field>
      ))}
    </div>
  );
}
