import { DialogButton, DropdownItem, Field, PanelSectionRow, SliderField, ToggleField } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { deviceApply, deviceForget, devicePerformance, PerformanceStatus, PerformanceValues, PowerLimitValues } from "../backend";
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

// Separate SPL, SPPT and FPPT (ADR-0084), through the Haversack Helper. The sliders are local until
// Apply, so moving one never writes to the firmware.
function LimitsEditor({ status, disabled, apply }: { status: PerformanceStatus; disabled: boolean; apply: (limits: PowerLimitValues) => void }) {
  const ranges = status.powerLimits?.ranges;
  const [values, setValues] = useState<PowerLimitValues | null>(
    ranges ? { spl: ranges.spl.current, sppt: ranges.sppt.current, fppt: ranges.fppt.current } : null,
  );
  if (!ranges || !values) return null;
  if (!status.powerLimits?.ready) {
    return (
      <Field
        label="Separate power limits"
        description={`Now SPL ${ranges.spl.current} W, SPPT ${ranges.sppt.current} W, FPPT ${ranges.fppt.current} W. Changing them separately needs the Haversack Helper: install it from Device, Reconnect help.`}
      />
    );
  }
  const words: Record<keyof PowerLimitValues, string> = {
    spl: "SPL, sustained (W)",
    sppt: "SPPT, slow boost (W)",
    fppt: "FPPT, fast boost (W)",
  };
  const set = (key: keyof PowerLimitValues, v: number) => {
    const next = { ...values, [key]: v };
    // Keep them rising: SPL <= SPPT <= FPPT.
    if (key === "spl") next.sppt = Math.max(next.sppt, v);
    if (key !== "fppt") next.fppt = Math.max(next.fppt, next.sppt);
    if (key === "fppt") next.sppt = Math.min(next.sppt, v);
    if (key !== "spl") next.spl = Math.min(next.spl, next.sppt);
    setValues(next);
  };
  return (
    <>
      <Field
        label="Separate power limits"
        description="Sustained, slow boost and fast boost power, each within the firmware's own range. Applying sets Custom mode. With a game running, they are kept for that game."
      />
      {(Object.keys(words) as (keyof PowerLimitValues)[]).map((key) => (
        <SliderField
          key={key}
          label={words[key]}
          value={values[key]}
          min={ranges[key].min}
          max={ranges[key].max}
          step={ranges[key].step}
          showValue
          disabled={disabled}
          onChange={(v) => set(key, v)}
        />
      ))}
      <Field label="Apply the limits" childrenLayout="inline">
        <DialogButton style={{ width: "auto" }} onClick={() => !disabled && apply(values)}>
          Apply
        </DialogButton>
      </Field>
    </>
  );
}

export function PowerPanel({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = usePerformance();
  const [busy, setBusy] = useState(false);
  if (!status) return null;
  // A function, not a component: a component defined here would be a new type on every render and
  // remount its rows, dropping the focus.
  const row = (child: React.ReactNode) => (compact ? <PanelSectionRow>{child}</PanelSectionRow> : child);
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
      toaster.toast({ title: "Haversack", body: plainError(err) });
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
              ? `${status.tools.join(", ")} manages performance on this device, so Haversack only shows it. Turn off its per-game profiles, or remove it, to let Haversack do this.`
              : game
                ? "Changes here are kept for the game you are playing and applied each time it starts. When it exits, Haversack puts back what was there before."
                : "Start a game to keep settings for it. A change made now lasts until something else changes it."
          }
        />
      )}
      {status.stopped && row(<Field label="Profile paused" description={status.stopped} />)}
      {current?.profile &&
        row(
          <DropdownItem
            label="Mode"
            disabled={busy || locked}
            rgOptions={current.profile.available.map((m) => ({ data: m, label: MODE_WORDS[m] ?? m }))}
            selectedOption={current.profile.current}
            onChange={(o) => void apply({ mode: String(o.data) })}
          />,
        )}
      {current?.tdp &&
        high > low &&
        row(
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
          />,
        )}
      {current?.boost != null && !compact && (
        <ToggleField label="CPU boost" checked={current.boost} disabled={busy || locked} onChange={(on) => void apply({ boost: on })} />
      )}
      {!compact && status.powerLimits?.available && (
        <LimitsEditor status={status} disabled={busy || locked} apply={(limits) => void apply({ limits })} />
      )}
      {!compact && game && status.profile && (
        <Field label="This game's profile" description={describe(status.profile)} childrenLayout="inline">
          <DialogButton
            style={{ width: "auto" }}
            disabled={busy}
            onClick={() =>
              void deviceForget(game)
                .then(setStatus)
                .catch((err) => toaster.toast({ title: "Haversack", body: plainError(err) }))
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
    [
      p.mode ? MODE_WORDS[p.mode] ?? p.mode : "",
      p.tdp ? `${p.tdp} W` : "",
      p.boost == null ? "" : `boost ${p.boost ? "on" : "off"}`,
      p.limits ? `SPL ${p.limits.spl}, SPPT ${p.limits.sppt}, FPPT ${p.limits.fppt} W` : "",
    ]
      .filter(Boolean)
      .join(", ") || "Nothing kept"
  );
}
