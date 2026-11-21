import { DialogButton, Field, Focusable, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useState } from "react";
import {
  ConfigSyncInfo,
  GameKind,
  gameConfigSync,
  SyncStatus,
  syncPull,
  syncPush,
  syncStatus,
  updateGameConfig,
} from "../backend";
import { agoText, CONFLICT_TEXT } from "../format";
import { openConflictModal } from "./ConflictModal";

function sharedText(info: ConfigSyncInfo | null): string {
  if (!info) return "";
  if (info.pending) return "Your latest changes will be shared with your other devices when the cloud is reachable.";
  if (!info.appliedFrom) return "Not shared yet.";
  return `Last changed on ${info.appliedFrom}, ${agoText(info.appliedAt)}.`;
}

export function SyncPanel({
  gameKey,
  enabled,
  kind,
  onEnabled,
}: {
  gameKey: string;
  enabled: boolean;
  kind: GameKind;
  onEnabled: (on: boolean) => void;
}) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [shared, setShared] = useState<ConfigSyncInfo | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    setStatus(await syncStatus(gameKey));
    setShared(await gameConfigSync(gameKey).catch(() => null));
  };

  useEffect(() => {
    void refresh();
  }, [gameKey]);

  const act = async (work: () => Promise<string>) => {
    setBusy(true);
    try {
      toaster.toast({ title: "Keepsake", body: await work() });
    } catch (err) {
      toaster.toast({ title: "Keepsake", body: String(err) });
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  if (status && !status.available) return <Field label="Sync" description={status.reason} />;

  const conflict = status?.conflict;

  return (
    <div>
      <ToggleField
        label="Sync this game"
        description={
          kind === "steam"
            ? "Steam games sync, back up and restore exactly like non-Steam games. If this game also uses Steam Cloud, Steam keeps a copy too, and Keepsake asks you whenever the two disagree."
            : "Keep this game's saves in step between your devices."
        }
        checked={enabled}
        onChange={(on) =>
          void updateGameConfig(gameKey, { enabled: on })
            .then(() => onEnabled(on))
            .then(refresh)
        }
      />
      <Field
        label="Sync status"
        description={[
          status?.base ? `Based on ${status.base}` : "Not synced yet",
          status?.lastPush ? `pushed ${agoText(status.lastPush)}` : "",
          status?.lastPull ? `pulled ${agoText(status.lastPull)}` : "",
          status?.pending ? "waiting for the cloud" : "",
          status?.sessionOpen ? "game session open" : "",
          status?.quarantined ? `a suspicious save was kept on this device (${status.quarantined})` : "",
        ]
          .filter(Boolean)
          .join(". ")}
      />
      {enabled && (
        <Field
          label="Shared settings"
          description={`Aliases, config files, custom paths and exclusions are shared with your other devices. ${sharedText(shared)}${
            shared?.concurrent.length
              ? ` Also changed at the same time on ${shared.concurrent.join(", ")}: the newest change was kept. Check the settings above.`
              : ""
          }`}
        />
      )}
      <Focusable style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() => void act(async () => `Check before play: ${JSON.stringify(await syncPull(gameKey))}`)}
        >
          Check before play
        </DialogButton>
        <DialogButton
          style={{ width: "auto" }}
          disabled={busy}
          onClick={() => void act(async () => `Save after play: ${JSON.stringify(await syncPush(gameKey))}`)}
        >
          Save after play
        </DialogButton>
      </Focusable>

      {conflict && (
        <Field
          label="Conflict"
          description={`${CONFLICT_TEXT[conflict.kind]} Nothing is pulled for this game until you choose.`}
          childrenLayout="inline"
        >
          <DialogButton style={{ width: "auto" }} disabled={busy} onClick={() => openConflictModal(gameKey, () => void refresh())}>
            Choose
          </DialogButton>
        </Field>
      )}
    </div>
  );
}
