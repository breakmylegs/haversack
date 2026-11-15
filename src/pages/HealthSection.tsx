import { DialogButton, Field } from "@decky/ui";
import { useEffect, useState } from "react";
import { HealthCheck, healthChecks, HealthStatus } from "../backend";
import { HEALTH_COLOURS, HEALTH_LABELS } from "../format";

// Build prompt section 15. Opening the page runs the checks without network; "Run checks"
// also tests the OneDrive connection.
export function HealthSection() {
  const [checks, setChecks] = useState<HealthCheck[] | null>(null);
  const [summary, setSummary] = useState<HealthStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (probe: boolean) => {
    setBusy(true);
    try {
      const result = await healthChecks(probe);
      setChecks(result.checks);
      setSummary(result.summary);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void run(false);
  }, []);

  return (
    <div>
      <Field
        label={summary ? `Health: ${HEALTH_LABELS[summary]}` : "Health"}
        description="Checks of sign-in, sync, conflicts, prefixes, the manifest and other save tools."
        childrenLayout="inline"
      >
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void run(true)}>
          {busy ? "Checking" : "Run checks"}
        </DialogButton>
      </Field>
      {error && <Field label="Checks failed" description={error} />}
      {(checks ?? []).map((c) => (
        <Field
          key={c.id}
          focusable
          label={
            <span>
              <span style={{ color: HEALTH_COLOURS[c.status] }}>{"●"} </span>
              {c.label}
            </span>
          }
          description={`${c.detail}${c.items.length ? ` ${c.items.slice(0, 8).join("; ")}` : ""}`}
        />
      ))}
    </div>
  );
}
