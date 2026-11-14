import { DialogButton, Field, Focusable } from "@decky/ui";
import { useEffect, useState } from "react";
import { getLogs, LogRecord } from "../backend";

const LIMIT = 200;

export function LogsPage() {
  const [records, setRecords] = useState<LogRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setRecords((await getLogs(LIMIT)).reverse());
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
      {error && <Field label="Could not read the log" description={error} />}
      {!error && records.length === 0 && <Field label="No log entries yet" />}
      {records.map((r, i) => (
        <Field
          key={`${r.ts}-${i}`}
          focusable
          label={`${r.ts}  ${r.level.toUpperCase()}  ${r.event}`}
          description={r.fields ? `${r.msg}  ${JSON.stringify(r.fields)}` : r.msg}
        />
      ))}
    </div>
  );
}
