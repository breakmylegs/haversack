import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { DeviceCheck, DeviceCheckResult, deviceCheckRun, deviceChecks, deviceChecksExport, deviceChecksRunAll } from "../backend";
import { QrCode } from "./QrCode";
import { plainError } from "../format";

const LABEL: Record<DeviceCheckResult["status"], string> = { pass: "Pass", warn: "Check", fail: "Fail", skip: "Skipped" };

// The device run's checks, inside the plugin: no SSH, terminal or laptop (ADR-0062).
export function DeviceChecks() {
  const [checks, setChecks] = useState<DeviceCheck[]>([]);
  const [results, setResults] = useState<Record<string, DeviceCheckResult>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [exported, setExported] = useState<{ file: string; where: string; summary: string } | null>(null);

  useEffect(() => {
    deviceChecks()
      .then((s) => {
        setChecks(s.checks);
        setResults(Object.fromEntries(s.results.map((r) => [r.id, r])));
      })
      .catch(() => undefined);
  }, []);

  const run = async (id: string) => {
    setBusy(id);
    try {
      const outcome = await deviceCheckRun(id);
      setResults((prev) => ({ ...prev, [id]: outcome }));
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(null);
    }
  };

  const runAll = async () => {
    setBusy("all");
    try {
      const s = await deviceChecksRunAll();
      setResults(Object.fromEntries(s.results.map((r) => [r.id, r])));
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(null);
    }
  };

  const exportResults = async () => {
    try {
      setExported(await deviceChecksExport());
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    }
  };

  return (
    <>
      <Field
        label="Device checks"
        description="Checks for the device run. Each shows pass or fail and what it found. Checks marked both need your other handheld paired, on and with Let other devices reach this one switched on. The export holds no names, addresses or paths."
        childrenLayout="below"
      >
        <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <DialogButton style={{ width: "auto" }} disabled={!!busy} onClick={() => void runAll()}>
            {busy === "all" ? "Running all checks" : "Run all"}
          </DialogButton>
          <DialogButton
            style={{ width: "auto" }}
            disabled={!!busy || Object.keys(results).length === 0}
            onClick={() => void exportResults()}
          >
            Export results
          </DialogButton>
        </Focusable>
      </Field>
      {checks.map((check) => {
        const r = results[check.id];
        return (
          <Field
            key={check.id}
            label={`${check.title}${check.needs === "both" ? " (both)" : ""}${r ? `: ${LABEL[r.status]}` : ""}`}
            description={r ? r.found : "Not run yet."}
            childrenLayout="below"
          >
            <DialogButton style={{ width: "auto" }} disabled={!!busy} onClick={() => void run(check.id)}>
              {busy === check.id ? "Running" : "Run"}
            </DialogButton>
          </Field>
        );
      })}
      {exported && (
        <Field
          label="Results saved"
          description={`Saved as ${exported.file} in ${exported.where}. Photograph the code or the summary below, or send the file.`}
          childrenLayout="below"
        >
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
            <QrCode text={exported.summary} size={320} />
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, margin: 0, maxWidth: 520 }}>{exported.summary}</pre>
          </div>
        </Field>
      )}
    </>
  );
}
