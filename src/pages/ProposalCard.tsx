import { DialogButton, Field, Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { IdentitySuggestion, MatchProposal, rejectMatch, setGameKey } from "../backend";
import { askApproveMatch } from "../matchApproval";
import { plainError } from "../format";

const SIGNAL_TEXT: Record<string, string> = {
  exe: "same program file",
  "exe-generic": "same common program file name",
  folder: "same install folder",
  name: "same name",
  "name-partial": "similar name",
  saves: "same save folders",
  "saves-partial": "some of the same save folders",
};

function label(s: IdentitySuggestion): string {
  return s.title ?? s.gameKey;
}

function why(s: IdentitySuggestion): string {
  return `${s.signals.map((x) => SIGNAL_TEXT[x] ?? x).join(", ")}, from ${s.sources.join(" and ")}`;
}

// A likely but uncertain match waiting for the user's decision (Peter, 15 November 2026).
export function ProposalCard({
  gameKey,
  gameName,
  proposal,
  onChanged,
}: {
  gameKey: string;
  gameName: string;
  proposal: MatchProposal;
  onChanged: () => void;
}) {
  const [choosing, setChoosing] = useState(false);

  const run = async (work: () => Promise<unknown>, done: string) => {
    try {
      await work();
      toaster.toast({ title: "Keepsake", body: done });
      onChanged();
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: `Not changed: ${plainError(err)}` });
    }
  };

  const approve = () => askApproveMatch(gameKey, gameName, proposal.candidate, onChanged);

  return (
    <Field
      label={`Is this ${label(proposal.candidate)}?`}
      description={`Keepsake thinks ${gameName} is the same game as ${label(proposal.candidate)} (${why(proposal.candidate)}), but is not certain. Approve it, choose another, or say it is not this game.`}
      childrenLayout="below"
    >
      <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <DialogButton style={{ width: "auto" }} onClick={approve}>
          Approve
        </DialogButton>
        <DialogButton style={{ width: "auto" }} onClick={() => setChoosing(!choosing)}>
          Choose another
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          onClick={() => void run(() => rejectMatch(gameKey), "Understood. That match will not be suggested again.")}
        >
          Not this game
        </DialogButton>
      </Focusable>
      {choosing && (
        <div style={{ marginTop: 8 }}>
          {proposal.alternatives.length === 0 && (
            <div style={{ fontSize: 12 }}>No other likely matches. Use "Change match" below to search the manifest.</div>
          )}
          {proposal.alternatives.map((alt) => (
            <Field key={alt.gameKey} label={label(alt)} description={why(alt)} childrenLayout="inline">
              <DialogButton
                style={{ width: "auto" }}
                onClick={() => void run(() => setGameKey(gameKey, alt.gameKey, alt.title), `${gameName} now syncs as ${label(alt)}.`)}
              >
                Use this
              </DialogButton>
            </Field>
          ))}
        </div>
      )}
    </Field>
  );
}
