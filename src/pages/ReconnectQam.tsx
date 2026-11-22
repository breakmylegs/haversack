import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { useEffect, useState } from "react";
import { RECONNECT_EVENT, ReconnectStatus, reconnectAssist, reconnectStatus } from "../backend";
import { plainError } from "../format";

// The quick menu's part of reconnect help (R22, ADR-0082): a Reconnect button for each helped
// controller that is not connected, and a note when a device may need help. Nothing when the
// Device module is off or no device has help.

export function ReconnectQam({ onOpen }: { onOpen: () => void }) {
  const [s, setS] = useState<ReconnectStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = () =>
    reconnectStatus()
      .then(setS)
      .catch(() => undefined);
  useEffect(() => {
    void load();
    const listener = addEventListener(RECONNECT_EVENT, () => void load());
    return () => {
      removeEventListener(RECONNECT_EVENT, listener);
    };
  }, []);
  if (!s?.available) return null;
  const helped = (s.devices ?? []).filter((d) => d.help && !d.connected);
  const suggested = (s.devices ?? []).some((d) => d.suggest && !d.help);
  return (
    <>
      {helped.map((d) => (
        <PanelSectionRow key={`${d.adapter}/${d.mac}`}>
          <ButtonItem
            layout="below"
            disabled={busy !== null}
            description={busy === d.mac ? "Looking for up to 30 seconds" : "Put it in pairing mode first"}
            onClick={async () => {
              setBusy(d.mac);
              try {
                const r = await reconnectAssist(d.adapter, d.mac);
                toaster.toast({ title: "Reconnect help", body: r.message });
              } catch (err) {
                toaster.toast({ title: "Reconnect help", body: plainError(err) });
              } finally {
                setBusy(null);
                void load();
              }
            }}
          >
            {`Reconnect ${d.name}`}
          </ButtonItem>
        </PanelSectionRow>
      ))}
      {suggested && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={onOpen}>
            A controller may need reconnect help
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
