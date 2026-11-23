import { DialogButton, Field } from "@decky/ui";
import { useEffect, useState } from "react";
import { ConflictEntry, listConflicts } from "../backend";
import { CONFLICT_TEXT, agoText } from "../format";
import { openConflictModal } from "./ConflictModal";

export function ConflictsPage() {
  const [conflicts, setConflicts] = useState<ConflictEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () =>
    listConflicts()
      .then((list) => {
        setConflicts(list);
        setError(null);
      })
      .catch((err) => setError(String(err)));

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <div>
      <Field
        label="Open conflicts"
        description="A conflict means two versions of a save exist and Haversack will not guess. Until you choose, the game plays with this device's save and is not pulled from the cloud."
      />
      {error && <Field label="Could not load conflicts" description={error} />}
      {conflicts && conflicts.length === 0 && <Field label="No conflicts" description="Every synced game agrees with the cloud." />}
      {(conflicts ?? []).map((c) => (
        <Field
          key={c.key}
          label={c.name}
          description={`${CONFLICT_TEXT[c.conflict.kind]} Raised ${agoText(c.conflict.raised)}.`}
          childrenLayout="inline"
        >
          <DialogButton style={{ width: "auto" }} onClick={() => openConflictModal(c.key, () => void refresh())}>
            Choose
          </DialogButton>
        </Field>
      ))}
    </div>
  );
}
