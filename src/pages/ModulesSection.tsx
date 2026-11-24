import { DialogButton, Field, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { modulesStatus, ModulesStatus, resetModule, setModuleEnabled } from "../backend";
import { HEALTH_LABELS, plainError } from "../format";

// v2 spec 7.3: each module with its switch, health and what it writes. A switched-off module runs nothing.
export function ModulesSection({ locked }: { locked: boolean }) {
  const [status, setStatus] = useState<ModulesStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    modulesStatus()
      .then(setStatus)
      .catch(() => undefined);
  }, []);

  const act = async (work: () => Promise<ModulesStatus>, done: string) => {
    setBusy(true);
    try {
      setStatus(await work());
      toaster.toast({ title: "Haversack", body: done });
    } catch (err) {
      toaster.toast({ title: "Haversack", body: `Not changed: ${plainError(err)}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <Field label="Modules" description="Haversack is made of modules. Each says what it writes, and a module that is off runs nothing." />
      {(status?.modules ?? []).map((m) => {
        const worst = m.health.some((c) => c.status === "fail") ? "fail" : m.health.some((c) => c.status === "warn") ? "warn" : "ok";
        const state = !m.available
          ? "Coming in a later version."
          : m.failed
            ? `Stopped after a problem: ${m.failed}`
            : m.running
              ? `Running. Health: ${HEALTH_LABELS[worst]}.`
              : "Off.";
        return m.available ? (
          <div key={m.name}>
            <ToggleField
              label={m.title}
              description={`${m.description} ${state} Writes: ${m.writes}`}
              checked={m.flag}
              disabled={locked || busy}
              onChange={(on) =>
                void act(() => setModuleEnabled(m.name, on), on ? `${m.title} switched on.` : `${m.title} switched off.`)
              }
            />
            {m.failed && (
              <DialogButton style={{ width: "auto", marginBottom: 8 }} disabled={busy} onClick={() => void act(() => resetModule(m.name), `Trying ${m.title} again.`)}>
                Try {m.title} again
              </DialogButton>
            )}
          </div>
        ) : (
          <Field key={m.name} focusable label={m.title} description={`${m.description} ${state}`} />
        );
      })}
      {status && !status.stateDatabase && (
        <Field label="State database unavailable" description="Modules that need it stay off." />
      )}
      {status && status.steamOpsPending > 0 && (
        <Field label={`${status.steamOpsPending} Steam changes waiting`} description="They are applied while Haversack runs in Gaming Mode." />
      )}
    </div>
  );
}
