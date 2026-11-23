import { DialogButton, Field, Focusable, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { qamShortcuts, QamShortcuts, setSetting, Shortcut } from "../backend";
import { plainError } from "../format";

// Settings, Quick menu (layout v3 addendum, ADR-0073): choose and order the shortcuts in
// Haversack's quick access menu panel. Up and Down move with the controller. Open Haversack is
// always there. Each change is saved at once and the panel follows straight away.

const KIND_WORDS: Record<Shortcut["kind"], string> = { page: "Opens a page", action: "Runs here", status: "Status line" };

export function ShortcutsEditor() {
  const [data, setData] = useState<QamShortcuts | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () =>
    qamShortcuts()
      .then(setData)
      .catch(() => undefined);
  useEffect(() => {
    void load();
  }, []);
  if (!data) return null;
  const offered = new Map(data.available.map((s) => [s.id, s]));
  const chosen = data.chosen.filter((id) => offered.has(id));
  const others = data.available.filter((s) => !chosen.includes(s.id));
  // Nothing here is disabled while saving: a focused control that turns disabled pushes the focus
  // away (v0.41.1). A second press while saving is simply ignored.
  const save = async (next: string[]) => {
    if (busy) return;
    setBusy(true);
    try {
      // Keep chosen shortcuts this device cannot show now (another module, a later version): they come back.
      const hidden = data.chosen.filter((id) => !offered.has(id));
      await setSetting("qamShortcuts", [...next, ...hidden]);
      await load();
    } catch (err) {
      toaster.toast({ title: "Haversack", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  const move = (index: number, by: number) => {
    const next = [...chosen];
    const [item] = next.splice(index, 1);
    next.splice(index + by, 0, item);
    void save(next);
  };
  return (
    <>
      <Field
        label="Quick menu shortcuts"
        description="Choose what Haversack's panel in the quick access menu shows, in order. Open Haversack is always there."
      />
      {chosen.map((id, index) => {
        const s = offered.get(id) as Shortcut;
        return (
          <div key={id}>
            <ToggleField
              label={`${index + 1}. ${s.label}`}
              description={KIND_WORDS[s.kind]}
              checked
              onChange={(on) => !on && void save(chosen.filter((c) => c !== id))}
            />
            <Focusable style={{ display: "flex", gap: 6, margin: "0 0 8px 16px" }}>
              <DialogButton style={{ width: "auto" }} onClick={() => index > 0 && move(index, -1)}>
                Up
              </DialogButton>
              <DialogButton style={{ width: "auto" }} onClick={() => index < chosen.length - 1 && move(index, 1)}>
                Down
              </DialogButton>
            </Focusable>
          </div>
        );
      })}
      {others.map((s) => (
        <ToggleField
          key={s.id}
          label={s.label}
          description={KIND_WORDS[s.kind]}
          checked={false}
          onChange={(on) => on && void save([...chosen, s.id])}
        />
      ))}
      <Field label="Start again" childrenLayout="inline">
        <DialogButton style={{ width: "auto" }} onClick={() => void save(data.defaults)}>
          Use the defaults
        </DialogButton>
      </Field>
    </>
  );
}
