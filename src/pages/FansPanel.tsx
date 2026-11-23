import { toaster } from "@decky/api";
import { DialogButton, DropdownItem, Field, Focusable, SliderField, ToggleField } from "@decky/ui";
import { useEffect, useRef, useState } from "react";
import { FanPoint, FansStatus, fansAssign, fansHandBack, fansSaveProfile, fansSelftest, fansSetOptions, fansStatus } from "../backend";
import { plainError } from "../format";

// Device, Fans (R24, ADR-0085). The Legion Go 2's fan follows a curve through the Haversack Helper;
// the Legion Go gets full fan speed. Readings refresh in place every few seconds: nothing on the
// page is removed or remounted by a refresh, so the focus stays where it is.

const toast = (body: string): void => {
  toaster.toast({ title: "Fans", body });
};
const MODE_WORDS: Record<string, string> = { "low-power": "Quiet", balanced: "Balanced", performance: "Performance", custom: "Custom" };

function readings(s: FansStatus): string {
  const d = s.device ?? {};
  return [
    s.temperature != null ? `${s.temperature.toFixed(0)} °C` : "no temperature",
    d.rpm != null ? `fan ${d.rpm} RPM` : "fan speed unknown",
    s.mode ? `mode ${MODE_WORDS[s.mode] ?? s.mode}` : "",
    s.active ? `profile ${s.active}${s.target ? `, asking ${s.target} RPM` : ""}` : "firmware in control",
  ]
    .filter(Boolean)
    .join(", ");
}

function CurveEditor({ s, reload }: { s: FansStatus; reload: (next?: FansStatus) => void }) {
  const settings = s.settings;
  const [name, setName] = useState(settings.default);
  const [points, setPoints] = useState<FanPoint[]>(settings.profiles[settings.default] ?? []);
  const [busy, setBusy] = useState(false);
  const pick = (profile: string) => {
    setName(profile);
    setPoints(settings.profiles[profile] ?? []);
  };
  const run = async (work: () => Promise<FansStatus>, done?: string) => {
    setBusy(true);
    try {
      reload(await work());
      if (done) toast(done);
    } catch (err) {
      toast(plainError(err));
    } finally {
      setBusy(false);
    }
  };
  const setPoint = (i: number, part: 0 | 1, value: number) => {
    const next = points.map((p) => [...p] as FanPoint);
    next[i][part] = value;
    // Keep the curve rising: later points never below an earlier one.
    for (let j = 1; j < next.length; j++) {
      if (next[j][0] <= next[j - 1][0]) next[j][0] = Math.min(100, next[j - 1][0] + 1);
      if (next[j][1] < next[j - 1][1]) next[j][1] = next[j - 1][1];
    }
    setPoints(next);
  };
  const top = s.limits.max;
  return (
    <>
      <DropdownItem
        label="Profile to edit"
        rgOptions={Object.keys(settings.profiles).map((p) => ({ data: p, label: p === settings.default ? `${p} (default)` : p }))}
        selectedOption={name}
        onChange={(o) => pick(String(o.data))}
      />
      {points.map((p, i) => (
        <div key={i}>
          <SliderField label={`Point ${i + 1}: temperature (°C)`} value={p[0]} min={20} max={100} step={1} showValue onChange={(v) => setPoint(i, 0, v)} />
          <SliderField label={`Point ${i + 1}: fan speed (RPM)`} value={p[1]} min={s.limits.min} max={top} step={100} showValue onChange={(v) => setPoint(i, 1, v)} />
        </div>
      ))}
      <Field label="Points" childrenLayout="below">
        <Focusable style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <DialogButton
            style={{ width: "auto" }}
            onClick={() => {
              const last = points[points.length - 1] ?? [80, 3000];
              if (points.length < 8) setPoints([...points, [Math.min(100, last[0] + 5), last[1]]]);
            }}
          >
            Add a point
          </DialogButton>
          <DialogButton style={{ width: "auto" }} onClick={() => points.length > 2 && setPoints(points.slice(0, -1))}>
            Remove the last point
          </DialogButton>
        </Focusable>
      </Field>
      <Field label="Save" childrenLayout="below">
        <Focusable style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <DialogButton style={{ width: "auto" }} onClick={() => !busy && void run(() => fansSaveProfile(name, points, false), `${name} saved.`)}>
            Save {name}
          </DialogButton>
          <DialogButton style={{ width: "auto" }} onClick={() => !busy && void run(() => fansAssign("default", "", name), `${name} is the default.`)}>
            Make it the default
          </DialogButton>
          {s.mode && (
            <DialogButton
              style={{ width: "auto" }}
              onClick={() => !busy && void run(() => fansAssign("mode", s.mode ?? "", name), `${name} for ${MODE_WORDS[s.mode ?? ""] ?? s.mode} mode.`)}
            >
              Use in {MODE_WORDS[s.mode] ?? s.mode} mode
            </DialogButton>
          )}
          {s.game != null && (
            <DialogButton style={{ width: "auto" }} onClick={() => !busy && void run(() => fansAssign("game", String(s.game), name), `${name} for this game.`)}>
              Use for this game
            </DialogButton>
          )}
        </Focusable>
      </Field>
    </>
  );
}

export function FansPanel() {
  const [s, setS] = useState<FansStatus | null>(null);
  const [unlockStep, setUnlockStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const live = useRef(true);
  const load = () =>
    fansStatus()
      .then((next) => live.current && setS(next))
      .catch(() => undefined); // keep what is shown
  useEffect(() => {
    live.current = true;
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      live.current = false;
      clearInterval(timer);
    };
  }, []);
  if (!s) return <Field label="Fans" description="Loading" />;
  if (s.off) return <Field label="Fans" description={s.problem ?? "Device controls are off."} />;
  const d = s.device ?? {};
  const go2 = d.model === "go2" || d.model === "go2-beta";
  const others = [...(d.conflicts ?? []), ...(s.tools ?? [])];
  const run = async (work: () => Promise<FansStatus | { status: FansStatus }>, done?: string) => {
    setBusy(true);
    try {
      const next = await work();
      setS("status" in next ? next.status : next);
      if (done) toast(done);
    } catch (err) {
      toast(plainError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Field label="Now" description={readings(s)} />
      {!s.helper.ready && (
        <Field
          label="Haversack Helper"
          description="Changing the fan needs the Haversack Helper: install it from Device, Reconnect help. The readings above need nothing."
        />
      )}
      {others.length > 0 && <Field label="Another fan control is active" description={`${others.join(", ")}. Haversack only shows the readings, so the two never fight.`} />}
      {s.problem && <Field label="Paused" description={s.problem} />}
      {s.helper.ready && !d.model && <Field label="Fan control" description="Fan control is for the Legion Go and Legion Go 2." />}
      {s.helper.ready && go2 && !d.validated && (
        <Field
          label="Fan test"
          description={`This BIOS and EC (${d.firmware?.bios ?? "?"}, EC ${d.firmware?.ec ?? "?"}) are not on the checked list (BIOS RRCN16WW with EC 1.16). The test asks for one speed for up to 15 seconds, checks the fan gets there, and gives the fan back.`}
        >
          <DialogButton onClick={() => !busy && void run(() => fansSelftest(), "Fan test finished.")}>{busy ? "Testing" : "Run the test"}</DialogButton>
        </Field>
      )}
      {s.helper.ready && go2 && d.validated && others.length === 0 && (
        <>
          <ToggleField
            label="Haversack controls the fan"
            description="Follows your curve, and gives the fan back to the firmware within seconds if Haversack stops. At 101 °C it runs at full speed whatever the curve says."
            checked={s.settings.enabled}
            onChange={(on) => !busy && void run(() => fansSetOptions({ enabled: on }))}
          />
          <ToggleField
            label="Smooth curve"
            description="Off: stepped, each point's speed holds until the next point."
            checked={s.settings.smooth}
            onChange={(on) => !busy && void run(() => fansSetOptions({ smooth: on }))}
          />
          {/* No key: a refresh must never remount the editor under the focus. */}
          <CurveEditor s={s} reload={(next) => next && setS(next)} />
          <ToggleField
            label="Unlock wider limits"
            description={`Lets curves reach ${5200} RPM. Off by default; the floor of ${s.limits.min} RPM and the 101 °C failsafe always stay.`}
            checked={s.settings.unlocked || unlockStep > 0}
            onChange={(on) => (on ? setUnlockStep(1) : void run(() => fansSetOptions({ unlocked: false })))}
          />
          {unlockStep === 1 && (
            <Field label="Wider limits run the fan beyond Lenovo's own maximum" description="Louder, and more wear on the fan. Select I understand to unlock.">
              <Focusable style={{ display: "flex", gap: 8 }}>
                <DialogButton onClick={() => void run(() => fansSetOptions({ unlocked: true, confirm: "I understand" })).then(() => setUnlockStep(0))}>
                  I understand
                </DialogButton>
                <DialogButton onClick={() => setUnlockStep(0)}>Cancel</DialogButton>
              </Focusable>
            </Field>
          )}
        </>
      )}
      {s.helper.ready && d.model === "go1" && others.length === 0 && (
        <>
          {d.fullSpeedAttribute ? (
            <ToggleField
              label="Full fan speed"
              description="Runs the fan flat out, held while Haversack runs; it switches off by itself within seconds if Haversack stops."
              checked={s.settings.fullSpeed}
              onChange={(on) => !busy && void run(() => fansSetOptions({ fullSpeed: on }))}
            />
          ) : (
            <Field label="Full fan speed" description="This kernel does not offer it yet (it arrives with kernel 7.2)." />
          )}
          <Field
            label="Fan curves on the Legion Go"
            description="The Legion Go's own fan table can only be changed through acpi_call, a kernel module SteamOS does not include and Haversack will not install. Curves arrive when the kernel offers them."
          />
        </>
      )}
      {s.helper.ready && (d.controlling || s.settings.enabled || s.settings.fullSpeed) && (
        <Field label="Give the fan back to the firmware" description="Switches Haversack's fan control off now.">
          <DialogButton onClick={() => !busy && void run(() => fansHandBack(), "The firmware controls the fan again.")}>Hand back</DialogButton>
        </Field>
      )}
    </>
  );
}
