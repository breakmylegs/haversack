import { ConfirmModal, DialogButton, Field, Focusable, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import {
  exportDiagnostics,
  freezeTest,
  getEnvironment,
  getGameProcesses,
  getSteamProbe,
  httpsTest,
  scrubCloud,
  simulateSyncJob,
  steamOpsList,
  steamProbe,
} from "../backend";
import { deckyMechanisms, runningAppDetails } from "../probes";
import { HealthSection } from "./HealthSection";
import { JsonBlock } from "./JsonBlock";
import { SigninProbe } from "./SigninProbe";

type Section = "environment" | "steam" | "processes" | "frontend" | "https" | "steamops" | "export" | "integrity";

const FREEZE_SECONDS = 5;
// Long enough to open Updates and try to install while it runs.
const SIMULATED_JOB_SECONDS = 60;

export function DiagnosticsPage() {
  const [results, setResults] = useState<Partial<Record<Section, unknown>>>({});
  const [busy, setBusy] = useState<Section | "freeze" | null>(null);

  const run = async (section: Section, work: () => Promise<unknown>) => {
    setBusy(section);
    try {
      const value = await work();
      setResults((prev) => ({ ...prev, [section]: value }));
    } catch (err) {
      setResults((prev) => ({ ...prev, [section]: { error: String(err) } }));
    } finally {
      setBusy(null);
    }
  };

  const runningAppId = (): number | undefined => SteamUIStore?.MainRunningAppID ?? undefined;

  const confirmFreeze = () => {
    const appid = runningAppId();
    if (!appid) {
      toaster.toast({ title: "Keepsake", body: "No game is running." });
      return;
    }
    showModal(
      <ConfirmModal
        strTitle="Freeze test"
        strDescription={`The running game will pause for ${FREEZE_SECONDS} seconds and then resume. A watchdog resumes it after 30 seconds at most, whatever happens.`}
        strOKButtonText="Run freeze test"
        strCancelButtonText="Cancel"
        onOK={async () => {
          setBusy("freeze");
          try {
            const result = await freezeTest(appid, FREEZE_SECONDS);
            toaster.toast({
              title: "Keepsake freeze test",
              body: result.ok
                ? `Paused ${result.stopped} processes and resumed ${result.resumed}.`
                : `Not run: ${result.reason ?? "unknown reason"}.`,
            });
          } finally {
            setBusy(null);
          }
        }}
      />,
    );
  };

  const frontendFacts = () => ({ decky: deckyMechanisms(), running: runningAppDetails() });

  return (
    <div>
      <HealthSection />
      <Field
        label="Diagnostics"
        description="Facts about this device for troubleshooting. The export is saved in Keepsake's settings folder on this device and includes the health checks."
      />
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
          onClick={() =>
            run("integrity", async () => {
              const report = await scrubCloud(true);
              return Object.values(report.games).map((g) => ({
                game: g.name,
                checked: g.checked,
                damaged: g.bad.length + g.missing.length,
                error: g.error,
              }));
            })
          }
        >
          Check cloud integrity
        </DialogButton>
        <DialogButton style={{ width: "auto" }} disabled={!!busy} onClick={confirmFreeze}>
          Freeze test
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          onClick={() => {
            toaster.toast({ title: "Keepsake", body: `Simulated sync job running for ${SIMULATED_JOB_SECONDS} seconds.` });
            simulateSyncJob(SIMULATED_JOB_SECONDS)
              .then(() => toaster.toast({ title: "Keepsake", body: "Simulated sync job finished." }))
              .catch(() => undefined);
          }}
        >
          Simulate sync job
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
      <SigninProbe />
    </div>
  );
}
