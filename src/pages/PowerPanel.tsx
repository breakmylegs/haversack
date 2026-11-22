import { DialogButton, DropdownItem, Field, PanelSectionRow, SliderField, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { deviceApply, deviceForget, devicePerformance, PerformanceStatus, PerformanceValues } from "../backend";
import { plainError } from "../format";

// Performance mode, TDP and CPU boost (R21 stage 2, ADR-0076), through steamos-manager only.
// While a game runs, a change is kept for that game and applied each time it starts.

const DEVICE_EVENT = "keepsake_device";

export const MODE_WORDS: Record<string, string> = {
  "low-power": "Quiet",
  balanced: "Balanced",
  "balanced-performance": "Balanced plus",
  performance: "Performance",
  custom: "Custom",
};

export function usePerformance(): [PerformanceStatus | null, (s: PerformanceStatus) => void] {
  const [status, setStatus] = useState<PerformanceStatus | null>(null);
  useEffect(() => {
    const load = () =>
      devicePerformance()
        .then(setStatus)
        .catch(() => undefined);
    void load();
    const listener = addEventListener(DEVICE_EVENT, () => void load());
    return () => removeEventListener(DEVICE_EVENT, listener);
  }, []);
  return [status, setStatus];
}

export function PowerPanel({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = usePerformance();
  const [busy, setBusy] = useState(false);
  if (!status) return null;
  const Row = ({ children }: { children: React.ReactNode }) => (compact ? <PanelSectionRow>{children}</PanelSectionRow> : <>{children}</>);
  if (status.off || !status.available) {
    return compact ? null : <Field label="Performance" description={status.problem ?? "Not available on this device."} />;
  }
  const current = status.current;
  const locked = status.tools.length > 0;
  const game = status.game;
  const apply = async (values: PerformanceValues) => {
    setBusy(true);
    try {
      setStatus(await deviceApply(values, game));
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  const low = Math.max(current?.tdp?.min ?? 0, status.limits.min ?? 0);
  const high = Math.min(current?.tdp?.max ?? 0, status.limits.max ?? 999);
  return (
    <>
      {!compact && (
        <Field
          label="Performance"
          description={
            locked
              ? `${status.tools.join(", ")} manages performance on this device, so Keepsake only shows it. Turn off its per-game profiles, or remove it, to let Keepsake do this.`
              : game
                ? "Changes here are kept for the game you are playing and applied each time it starts. When it exits, Keepsake puts back what was there before."
                : "Start a game to keep settings for it. A change made now lasts until something else changes it."
          }
        />
      )}
      {status.stopped && (
        <Row>
          <Field label="Profile paused" description={status.stopped} />
        </Row>
      )}
      {current?.profile && (
        <Row>
          <DropdownItem
            label="Mode"
            disabled={busy || locked}
            rgOptions={current.profile.available.map((m) => ({ data: m, label: MODE_WORDS[m] ?? m }))}
            selectedOption={current.profile.current}
            onChange={(o) => void apply({ mode: String(o.data) })}
          />
        </Row>
      )}
      {current?.tdp && high > low && (
        <Row>
          <SliderField
            label="TDP (W)"
            description={compact ? undefined : "Sets Custom mode: the firmware uses power limits only there."}
            value={Math.min(high, Math.max(low, current.tdp.value))}
            min={low}
            max={high}
            step={1}
            showValue
            disabled={busy || locked}
            onChange={(v) => void apply({ tdp: v })}
          />
        </Row>
      )}
      {current?.boost != null && !compact && (
        <ToggleField label="CPU boost" checked={current.boost} disabled={busy || locked} onChange={(on) => void apply({ boost: on })} />
      )}
      {!compact && game && status.profile && (
        <Field label="This game's profile" description={describe(status.profile)} childrenLayout="inline">
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() =>
              void deviceForget(game)
                .then(setStatus)
                .catch((err) => toaster.toast({ title: "Keepsake", body: plainError(err) }))
            }
          >
            Forget it
          </DialogButton>
        </Field>
      )}
    </>
  );
}

export function describe(p: PerformanceValues): string {
  return (
    [p.mode ? MODE_WORDS[p.mode] ?? p.mode : "", p.tdp ? `${p.tdp} W` : "", p.boost == null ? "" : `boost ${p.boost ? "on" : "off"}`]
      .filter(Boolean)
      .join(", ") || "Nothing kept"
  );
}
