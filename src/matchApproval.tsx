import { ConfirmModal, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { approveMatch } from "./backend";
import { plainError } from "./format";

type Candidate = { gameKey: string; title: string | null };

// The one confirmation for approving an uncertain match, used by the game's page and the Games list row.
export function askApproveMatch(gameKey: string, gameName: string, candidate: Candidate, onChanged: () => void): void {
  const label = candidate.title ?? candidate.gameKey;
  showModal(
    <ConfirmModal
      strTitle="Use this match?"
      strDescription={`${gameName} will sync as ${label}. If both devices have different saves, Haversack asks you which to keep before anything is replaced.`}
      strOKButtonText="Approve"
      strCancelButtonText="Not yet"
      onOK={() =>
        void approveMatch(gameKey)
          .then(() => {
            toaster.toast({ title: "Haversack", body: `${gameName} now syncs as ${label}.` });
            onChanged();
          })
          .catch((err) => toaster.toast({ title: "Haversack", body: `Not changed: ${plainError(err)}` }))
      }
    />,
  );
}
