import { DialogButton, Field, Focusable } from "@decky/ui";
import { useEffect, useState } from "react";
import { FaExclamationTriangle, FaInfoCircle } from "react-icons/fa";
import { activity, ActivityEntry } from "../backend";
import { isoText, STATUS } from "../format";

// What Keepsake did, newest first, in plain words (ADR-0048). The detailed log stays in Logs.
export function ActivityPage() {
  const [entries, setEntries] = useState<ActivityEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setEntries(await activity(100));
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <div>
      <Focusable style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <DialogButton style={{ width: "auto" }} onClick={() => void refresh()}>
          Refresh
        </DialogButton>
      </Focusable>
      {error && <Field label="Could not read the activity" description={error} />}
      {entries && entries.length === 0 && <Field label="Nothing yet" description="Syncs, restores and checkpoints appear here." />}
      {(entries ?? []).map((e, i) => (
        <Field
          key={`${e.time}-${i}`}
          focusable
          label={
            <span>
              {e.level === "warn" ? <FaExclamationTriangle style={{ color: STATUS.warn }} /> : <FaInfoCircle />} {e.text}
            </span>
          }
          description={e.time ? isoText(e.time) : undefined}
        />
      ))}
    </div>
  );
}
