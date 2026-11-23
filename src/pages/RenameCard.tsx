import { ButtonItem, ConfirmModal, PanelSection, PanelSectionRow, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { RenameStatus } from "../backend";
import { plainError } from "../format";
import { canRemoveOld, removeOldAndFinish } from "../rename";

// The quick menu while Haversack waits for the old Keepsake to go (ADR-0089): nothing else is shown,
// because nothing else has started.
export function RenameCard({ status }: { status: RenameStatus }) {
  const [working, setWorking] = useState(false);
  const [problem, setProblem] = useState("");

  const finish = async () => {
    setWorking(true);
    setProblem("");
    try {
      const after = await removeOldAndFinish(status);
      if (after.started) {
        const files = after.moved?.files ?? 0;
        toaster.toast({ title: "Haversack", body: files ? `Moved across and checked ${files} files. Welcome to Haversack.` : "Welcome to Haversack." });
      } else if (after.error) setProblem(`Nothing was changed: ${after.error}. Try again.`);
      else if (after.hold) setProblem("Keepsake is still installed. Remove it in Decky's settings, then press Finish.");
    } catch (err) {
      setProblem(plainError(err));
    } finally {
      setWorking(false);
    }
  };

  const confirm = () =>
    showModal(
      <ConfirmModal
        strTitle="Remove the old Keepsake?"
        strDescription={`Haversack copies your settings, sign-ins and history across, checks every file, then starts. The old copy stays on this device, so nothing is lost. This removes the Keepsake plugin${status.oldHelper ? " and Keepsake Helper" : ""} through Decky.`}
        strOKButtonText="Remove and move across"
        strCancelButtonText="Not now"
        onOK={() => void finish()}
      />,
    );

  return (
    <PanelSection title="Haversack">
      <PanelSectionRow>
        <div style={{ fontSize: 12 }}>
          {status.hold
            ? "Keepsake is now called Haversack. Haversack starts once the old Keepsake plugin is removed, so the two never sync at once. Until then, Keepsake keeps working as before."
            : status.error
              ? `Moving Keepsake's data across did not finish: ${status.error}. Nothing was changed.`
              : "Starting"}
        </div>
      </PanelSectionRow>
      {status.hold && canRemoveOld() && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={working} onClick={confirm}>
            {working ? "Working" : "Remove the old Keepsake"}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {(status.error || (status.hold && !canRemoveOld())) && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={working} onClick={() => void finish()}>
            {working ? "Working" : "Finish"}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {problem && (
        <PanelSectionRow>
          <div style={{ fontSize: 12 }}>{problem}</div>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
