import { ConfirmModal, DialogButton, Field, Focusable, PanelSectionRow, showModal } from "@decky/ui";
import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  GameTransfer,
  replicationActivity,
  replicationClearGame,
  replicationGetGame,
  replicationPeerGames,
  replicationStopGame,
  TransferStage,
} from "../backend";
import { plainError } from "../format";

// Games moving between devices, as one bar each, on both devices (v0.31.0, ADR-0072).
// The bars live in the backend, so they carry on while a page is closed and reopened.

const REPLICATION_EVENT = "keepsake_replication";

export const STAGE_LABELS: Record<TransferStage, string> = {
  "checking-space": "Checking space",
  preparing: "Preparing",
  copying: "Copying",
  verifying: "Verifying",
  adding: "Adding to Steam",
  done: "Done",
  failed: "Failed",
  paused: "Paused",
  waiting: "Waiting",
};

const MOVING: TransferStage[] = ["checking-space", "preparing", "copying", "verifying", "adding", "waiting"];

export function gib(bytes: number): string {
  return `${(bytes / 2 ** 30).toFixed(1)} GiB`;
}

export function speedText(bytesPerSecond: number): string {
  return bytesPerSecond >= 1e6 ? `${(bytesPerSecond / 1e6).toFixed(0)} MB/s` : `${(bytesPerSecond / 1e3).toFixed(0)} KB/s`;
}

export function leftText(seconds: number): string {
  if (seconds < 60) return "under a minute left";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min left`;
  return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min left`;
}

/** "42% · 3.1 of 7.4 GiB · 85 MB/s · 2 min left", or as much of it as is known. */
export function transferLine(t: GameTransfer): string {
  const parts: string[] = [];
  if (t.total) parts.push(`${t.percent}%`, `${gib(t.done).replace(" GiB", "")} of ${gib(t.total)}`);
  if (t.stage === "copying" && t.bytesPerSecond) parts.push(speedText(t.bytesPerSecond));
  if (t.stage === "copying" && t.secondsLeft != null) parts.push(leftText(t.secondsLeft));
  return parts.join(" · ");
}

export function whereText(t: GameTransfer): string {
  return t.direction === "sending" ? `to ${t.peer}` : `from ${t.peer}`;
}

/** Follows the bars: on every Replication event, and every second while something moves. */
export function useGameTransfers(): [GameTransfer[], () => Promise<void>] {
  const [items, setItems] = useState<GameTransfer[]>([]);
  const refresh = () =>
    replicationActivity()
      .then(setItems)
      .catch(() => setItems([]));
  useEffect(() => {
    void refresh();
    const listener = addEventListener(REPLICATION_EVENT, () => void refresh());
    return () => removeEventListener(REPLICATION_EVENT, listener);
  }, []);
  const moving = items.some((t) => MOVING.includes(t.stage));
  useEffect(() => {
    if (!moving) return;
    const timer = setInterval(() => void refresh(), 1000);
    return () => clearInterval(timer);
  }, [moving]);
  return [items, refresh];
}

export function Bar({ percent, failed, height = 8 }: { percent: number; failed?: boolean; height?: number }) {
  return (
    <div style={{ background: "rgba(255,255,255,0.15)", borderRadius: height / 2, height, overflow: "hidden", margin: "4px 0" }}>
      <div
        style={{
          width: `${Math.max(0, Math.min(100, percent))}%`,
          height: "100%",
          background: failed ? "#d9534f" : "#1a9fff",
          transition: "width 0.8s linear",
        }}
      />
    </div>
  );
}

function stopModal(t: GameTransfer, after: () => void) {
  const here = t.direction === "receiving";
  showModal(
    <ConfirmModal
      strTitle={`Stop and remove ${t.title}?`}
      strDescription={
        here
          ? "Everything this copy made on this device is deleted: the game's folder, its prefix, a copied compatibility tool and its Steam shortcut. Nothing else is touched."
          : `${t.peer} is asked to stop and delete everything this copy made there. The game on this device is not touched.`
      }
      strOKButtonText="Stop and remove"
      strCancelButtonText="Cancel"
      onOK={() =>
        void replicationStopGame(t.id)
          .then(() => toaster.toast({ title: "Keepsake", body: `${t.title} stopped and removed.` }))
          .catch((err) => toaster.toast({ title: "Keepsake", body: plainError(err) }))
          .finally(after)
      }
    />,
  );
}

/** The full bars, with Stop and remove or Clear, for the Devices page. */
export function GameTransfersSection() {
  const [items, refresh] = useGameTransfers();
  if (!items.length) return null;
  return (
    <>
      <Field label="Games moving between devices" />
      {items.map((t) => (
        <Field
          key={t.id}
          label={`${t.title} ${whereText(t)}: ${STAGE_LABELS[t.stage]}`}
          description={[transferLine(t), t.reason ?? ""].filter(Boolean).join(". ")}
          childrenLayout="below"
        >
          <Bar percent={t.percent} failed={t.stage === "failed"} />
          <Focusable style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {t.canStop && (
              <DialogButton style={{ width: "auto" }} onClick={() => stopModal(t, () => void refresh())}>
                Stop and remove
              </DialogButton>
            )}
            {t.canClear && (
              <DialogButton
                style={{ width: "auto" }}
                onClick={() =>
                  void replicationClearGame(t.id)
                    .catch((err) => toaster.toast({ title: "Keepsake", body: plainError(err) }))
                    .finally(() => void refresh())
                }
              >
                Clear
              </DialogButton>
            )}
          </Focusable>
        </Field>
      ))}
    </>
  );
}

/** One compact line per game for the quick access menu. */
export function GameTransfersCompact({ onOpen }: { onOpen: () => void }) {
  const [items] = useGameTransfers();
  const shown = items.filter((t) => MOVING.includes(t.stage) || t.stage === "failed");
  if (!shown.length) return null;
  return (
    <PanelSectionRow>
    <Focusable onActivate={onOpen} style={{ fontSize: 12, padding: "4px 0" }}>
      {shown.map((t) => (
        <div key={t.id} style={{ marginBottom: 6 }}>
          <div>
            {t.title} {whereText(t)}: {STAGE_LABELS[t.stage]}
            {t.total && t.stage !== "failed" ? ` ${t.percent}%` : ""}
            {t.stage === "copying" && t.secondsLeft != null ? `, ${leftText(t.secondsLeft)}` : ""}
          </div>
          <Bar percent={t.percent} failed={t.stage === "failed"} height={4} />
        </div>
      ))}
    </Focusable>
    </PanelSectionRow>
  );
}

/** "Games on <device>": get a game from a paired device (ADR-0072). */
export function PeerGames({ peerId, peerName }: { peerId: string; peerName: string }) {
  const [games, setGames] = useState<{ id: string; title: string }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const load = async () => {
    setBusy(true);
    try {
      setGames(await replicationPeerGames(peerId));
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: plainError(err) });
    } finally {
      setBusy(false);
    }
  };
  const get = (game: { id: string; title: string }) =>
    showModal(
      <ConfirmModal
        strTitle={`Get ${game.title} from ${peerName}?`}
        strDescription="Keepsake checks there is space here, then copies the game, its prefix and, if this device lacks it, its compatibility tool, and adds it to Steam with its artwork and launch options. Nothing here is replaced."
        strOKButtonText="Get this game"
        strCancelButtonText="Cancel"
        onOK={() =>
          void replicationGetGame(peerId, game.id, game.title)
            .then(() => toaster.toast({ title: "Keepsake", body: `${game.title} is coming from ${peerName}.` }))
            .catch((err) => toaster.toast({ title: "Keepsake", body: plainError(err) }))
        }
      />,
    );
  if (games === null) {
    return (
      <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void load()}>
        {busy ? "Looking" : `Games on ${peerName}`}
      </DialogButton>
    );
  }
  return (
    <Field label={`Games on ${peerName}`} description={games.length ? undefined : "No non-Steam games there."} childrenLayout="below">
      <Focusable style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {games.map((g) => (
          <DialogButton key={g.id} style={{ width: "auto", textAlign: "left" }} onClick={() => get(g)}>
            Get this game: {g.title}
          </DialogButton>
        ))}
        <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => void load()}>
          Refresh the list
        </DialogButton>
      </Focusable>
    </Field>
  );
}
